"""Workflow automation — evaluate rules and fire actions."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def get_rules(team_id: str) -> list[dict]:
    """Fetch active workflow rules for a team."""
    try:
        import src.core.db as db  # noqa: PLC0415

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
        import src.core.db as db  # noqa: PLC0415

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
        import src.core.db as db  # noqa: PLC0415

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


# Below this percentage a standup counts as low participation, unless a rule
# sets its own figure. The participation.low webhook uses the same default.
LOW_PARTICIPATION_THRESHOLD = 50


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
        threshold = int(rule.get("condition_value") or LOW_PARTICIPATION_THRESHOLD)
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
    from src.core.url_guard import is_safe_webhook_url  # noqa: PLC0415

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
        from src.modules.standup.handlers import deliver_webhook  # noqa: PLC0415
    except Exception as exc:
        logger.warning("Cannot deliver webhook for rule %s: %s", rule_id, exc)
        return

    hook = {"id": None, "webhook_url": target, "secret": None}
    try:
        import src.core.db as db  # noqa: PLC0415

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


def schedule_participation_pct(
    team_id: str, schedule: dict | None, local_day: date, answered: set[str], eligible: set[str]
) -> int:
    """Percentage of one standup's expected members who answered on `local_day`.

    Expected means on this standup (everyone eligible when it names nobody),
    eligible (active, not on leave) and not skipping today. Returns 100 when
    nobody was expected, so an empty or fully skipped day never trips a rule.
    """
    import src.core.db as db  # noqa: PLC0415
    from src.core.scheduler import participation_pct  # noqa: PLC0415

    participants = [p for p in ((schedule or {}).get("participants") or []) if p]
    pool = list(dict.fromkeys(participants)) if participants else sorted(eligible)
    stats = []
    for user_id in pool:
        if user_id not in eligible:
            continue
        try:
            if db.is_skipped_today(team_id, user_id, for_date=local_day):
                continue
        except Exception as exc:
            logger.debug("Skip lookup failed for %s/%s: %s", team_id, user_id, exc)
        stats.append({"user_id": user_id, "enrolled": True, "responses": 1 if user_id in answered else 0})
    return participation_pct(stats)


def evaluate_low_participation(
    team_id: str, schedule: dict | None, local_day: date, today_standups: list[dict], client
) -> None:
    """Fire low_participation rules for one standup, once its window has closed."""
    try:
        from src.core.roster import eligible_members  # noqa: PLC0415

        eligible = {m.user_id for m in eligible_members(team_id)}
        answered = {s.get("user_id") for s in today_standups or [] if s.get("user_id")}
        pct = schedule_participation_pct(team_id, schedule, local_day, answered, eligible)
        context = {"participation_pct": pct, "team": team_id, "standup": (schedule or {}).get("name") or ""}
        evaluate_rules(team_id, "low_participation", context, client)
    except Exception as exc:
        logger.warning("Participation workflow rules failed for %s: %s", team_id, exc)
        return

    # participation.low was offered as a webhook event but never sent.
    try:
        from src.modules.standup.handlers import fire_webhooks  # noqa: PLC0415

        if pct < LOW_PARTICIPATION_THRESHOLD:
            fire_webhooks(
                team_id,
                "participation.low",
                {
                    "team_id": team_id,
                    "schedule_id": (schedule or {}).get("id"),
                    "schedule": (schedule or {}).get("name") or "",
                    "date": local_day.isoformat(),
                    "participation_pct": pct,
                    "threshold": LOW_PARTICIPATION_THRESHOLD,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
    except Exception as exc:
        logger.warning("participation.low webhook failed for %s: %s", team_id, exc)
