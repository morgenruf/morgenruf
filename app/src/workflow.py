"""Workflow automation — evaluate rules and fire actions."""

from __future__ import annotations

import logging

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def get_rules(team_id: str) -> list[dict]:
    """Fetch active workflow rules for a team."""
    try:
        import db  # noqa: PLC0415

        if db._pool is None:
            return []
        sql = """
            SELECT id, team_id, name, trigger, condition_value,
                   action, action_target, action_message, active, created_at
            FROM workflow_rules
            WHERE team_id = %s AND active = TRUE
            ORDER BY id
        """
        with db.db_conn() as conn:
            import psycopg2.extras  # noqa: PLC0415

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (team_id,))
                rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("get_rules failed for %s: %s", team_id, exc)
        return []


def save_rule(
    team_id: str,
    name: str,
    trigger: str,
    condition_value: str | None,
    action: str,
    action_target: str,
    action_message: str | None,
) -> int | None:
    """Insert a new workflow rule and return its id."""
    try:
        import db  # noqa: PLC0415

        if db._pool is None:
            return None
        sql = """
            INSERT INTO workflow_rules
                (team_id, name, trigger, condition_value, action, action_target, action_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        with db.db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (team_id, name, trigger, condition_value, action, action_target, action_message))
                row = cur.fetchone()
                conn.commit()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("save_rule failed for %s: %s", team_id, exc)
        return None


def delete_rule(rule_id: int, team_id: str) -> None:
    """Soft-delete a workflow rule (set active=False)."""
    try:
        import db  # noqa: PLC0415

        if db._pool is None:
            return
        sql = "UPDATE workflow_rules SET active = FALSE WHERE id = %s AND team_id = %s"
        with db.db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (rule_id, team_id))
                conn.commit()
    except Exception as exc:
        logger.warning("delete_rule failed for %s/%s: %s", rule_id, team_id, exc)


def _render_message(template: str | None, default: str, context: dict) -> str:
    """Render a message template with context variables."""
    msg = template or default
    try:
        msg = msg.replace("{team}", str(context.get("team", "")))
        msg = msg.replace("{trigger}", str(context.get("trigger", "")))
        msg = msg.replace("{blockers}", str(context.get("blockers", "")))
        msg = msg.replace("{participation}", str(context.get("participation_pct", "")))
    except Exception as e:
        logger.warning("Unexpected error in _render_message applying template: %s", e)
    return msg


def evaluate_rules(team_id: str, trigger: str, context: dict, client) -> None:
    """Load active rules matching trigger and fire their actions."""
    try:
        rules = get_rules(team_id)
        matching = [r for r in rules if r["trigger"] == trigger]
        for rule in matching:
            try:
                _fire_rule(team_id, rule, trigger, context, client)
            except Exception as exc:
                logger.warning("Rule %s (%s) failed: %s", rule.get("id"), rule.get("name"), exc)
    except Exception as exc:
        logger.warning("evaluate_rules failed for %s/%s: %s", team_id, trigger, exc)


def _fire_rule(team_id: str, rule: dict, trigger: str, context: dict, client) -> None:
    """Evaluate condition and execute action for a single rule."""
    # Condition check
    if trigger == "blocker_detected":
        if not context.get("has_blockers", False):
            return
    elif trigger == "low_participation":
        threshold = int(rule.get("condition_value") or 50)
        if context.get("participation_pct", 100) >= threshold:
            return
    # standup_complete: always fires

    action = rule["action"]
    target = rule["action_target"]
    default_msg = f"[Morgenruf] Trigger: {trigger} | Team: {context.get('team', '')}"
    msg = _render_message(rule.get("action_message"), default_msg, {**context, "trigger": trigger})

    if action in ("post_to_channel", "send_dm"):
        client.chat_postMessage(channel=target, text=msg)
        logger.info("Rule %s fired %s → %s", rule.get("id"), action, target)
    elif action == "fire_webhook":
        _fire_rule_webhook(team_id, rule, trigger, context)
    else:
        logger.warning("Unknown action %r in rule %s", action, rule.get("id"))


def _fire_rule_webhook(team_id: str, rule: dict, trigger: str, context: dict) -> None:
    """POST a rule's payload, validated and signed like any other webhook.

    Two things were wrong with the original one-liner (#81). It POSTed straight
    to `action_target` with no `is_safe_webhook_url` check, so a rule could aim
    the server at the cloud metadata endpoint or an internal port. And it sent
    nothing a receiver could verify, while registered webhooks had been signed
    since #73.

    Both are fixed by reusing the registered-webhook delivery path. When the
    target matches a webhook this workspace has registered, the delivery is
    signed with that webhook's secret and recorded in the delivery log. When it
    does not, it still goes out, but unsigned and flagged as such in the log, so
    the gap is visible rather than silent.
    """
    from url_guard import is_safe_webhook_url  # noqa: PLC0415

    target = (rule.get("action_target") or "").strip()
    rule_id = rule.get("id")

    if not is_safe_webhook_url(target):
        logger.warning(
            "Rule %s webhook refused: %r is not an allowed target",
            rule_id,
            target,
        )
        return

    try:
        from handlers import deliver_webhook  # noqa: PLC0415
    except Exception as exc:
        logger.warning("Cannot deliver webhook for rule %s: %s", rule_id, exc)
        return

    hook = {"id": None, "webhook_url": target, "secret": None}
    try:
        import db  # noqa: PLC0415

        for registered in db.get_webhooks(team_id) or []:
            if (registered.get("webhook_url") or "").strip() == target:
                hook = registered
                break
    except Exception as exc:
        # A lookup failure only costs the signature, so deliver anyway.
        logger.warning("Could not match rule %s target to a registered webhook: %s", rule_id, exc)

    result = deliver_webhook(hook, f"rule.{trigger}", context, team_id=team_id)
    logger.info(
        "Rule %s fired webhook to %s (signed=%s, status=%s)",
        rule_id,
        target,
        result.get("signed"),
        result.get("status_code"),
    )
