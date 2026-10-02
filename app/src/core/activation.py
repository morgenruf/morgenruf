"""Getting a new workspace from install to a team that uses Morgenruf.

Of the outside workspaces that removed the app, nearly all had never set up a
standup, and most of the rest never got a single answer. Two pieces push the
installer through the first week:

* The checklist: five steps at the top of App Home for workspace admins, each
  computed from data already stored, each with the button that does it. It
  goes away when every step is done or an admin hides it.
* Nudges: one Slack DM to the installer on day 2 (no standup yet), day 3 (a
  standup but no answer) and day 7 (fewer than three steps done). Each is
  recorded before it is sent, so it can never go twice, and the operator's
  own workspaces are never nudged.

No new scopes, commands or events: buttons on App Home and in DMs only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from slack_sdk import WebClient

logger = logging.getLogger(__name__)

KIND = "nudge:day2"
AFTER_HOURS = 48
TEXT = "Morgenruf is installed but no standup is running yet. It takes two fields: pick your team's channel and a time."

KIND_DAY3 = "nudge:day3"
DAY3_HOURS = 72
KIND_DAY7 = "nudge:day7"
DAY7_HOURS = 168
DAY7_BELOW = 3

HIDE_ACTION = "activation:hide"
INVITE_HELP_ACTION = "activation:invite_help"
SEND_NOW_ACTION = "activation:send_now"
PICK_ACTION = "activation:pick_rituals"
PICK_CALLBACK = "activation:rituals"
MEMBERS_ACTION = "activation:members"

# Anything beyond the standup that gives a team a second reason to stay.
RITUALS = ("kudos", "connect", "celebrations", "polls", "watercooler")
# "Get the first answers" is done once this many different people answered.
FIRST_ANSWERS = 2

INVITE_HELP = (
    "Add @Morgenruf to your standup's channel:\n"
    "1. Open the channel and click its name at the top.\n"
    "2. Choose *Integrations*, then *Add apps*.\n"
    "3. Pick *Morgenruf*.\n\n"
    "A standup made with the quick start switches itself on as soon as the bot is in."
)


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    hint: str
    done: bool
    button: str
    action: str


def _bot_token(team_id: str, stored: str) -> str:
    """The stored token, refreshed first when it is a rotating one near expiry."""
    from src.core.scheduler import _fresh_bot_token  # noqa: PLC0415

    return _fresh_bot_token(team_id, stored)


# ── The checklist ───────────────────────────────────────────────────────────


def _rituals_on(team_id: str) -> bool:
    from src.core.modules import is_active_for  # noqa: PLC0415

    return any(is_active_for(team_id, name) for name in RITUALS)


def steps(state: dict, rituals_on: bool) -> list[Step]:
    """The five steps for one workspace, from db.checklist_state. No I/O."""
    from src.core.quickstart_button import OPEN_ACTION  # noqa: PLC0415

    has_standup = bool(state.get("has_standup"))
    return [
        Step(
            "standup",
            "Start a standup",
            "Pick a channel and a time. Two fields.",
            has_standup,
            "Quick start",
            OPEN_ACTION,
        ),
        Step(
            "invite",
            "Add @Morgenruf to its channel",
            "The bot can only post where it has been added.",
            has_standup and not state.get("awaiting_invite"),
            "How to",
            INVITE_HELP_ACTION,
        ),
        Step(
            "answers",
            "Get the first answers",
            "Send today's questions now instead of waiting for tomorrow.",
            int(state.get("responders") or 0) >= FIRST_ANSWERS,
            "Send it now",
            SEND_NOW_ACTION,
        ),
        Step(
            "ritual",
            "Add one more ritual",
            "Kudos, coffee chats, celebrations, polls or watercooler questions.",
            rituals_on,
            "Pick one",
            PICK_ACTION,
        ),
        Step(
            "share",
            "Share the load",
            "Make someone else an admin, or a manager of one standup.",
            bool(state.get("shared")),
            "Open Members",
            MEMBERS_ACTION,
        ),
    ]


def steps_for(team_id: str) -> list[Step]:
    import src.core.db as db  # noqa: PLC0415

    return steps(db.checklist_state(team_id), _rituals_on(team_id))


def done_count(team_id: str) -> int:
    return sum(1 for s in steps_for(team_id) if s.done)


def _button(step: Step) -> dict:
    return {
        "type": "button",
        "action_id": step.action,
        "text": {"type": "plain_text", "text": step.button},
        **({"style": "primary"} if step.action == SEND_NOW_ACTION else {}),
    }


def checklist_blocks(team_id: str, user_id: str) -> list[dict]:
    """The card for the top of App Home. Workspace admins only; empty when done or hidden."""
    import src.core.db as db  # noqa: PLC0415

    if db.can_administer(team_id, user_id) is not True:
        return []
    state = db.checklist_state(team_id)
    if not state or state.get("hidden_at"):
        return []
    all_steps = steps(state, _rituals_on(team_id))
    done = sum(1 for s in all_steps if s.done)
    if done == len(all_steps):
        return []
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Get your team going* · {done} of {len(all_steps)} done"},
            "accessory": {"type": "button", "action_id": HIDE_ACTION, "text": {"type": "plain_text", "text": "Hide"}},
        }
    ]
    for step in all_steps:
        if step.done:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"✅ ~{step.title}~"}})
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"⬜ *{step.title}*\n{step.hint}"},
                    "accessory": _button(step),
                }
            )
    blocks.append({"type": "divider"})
    return blocks


# ── What the buttons do ─────────────────────────────────────────────────────


def send_now(team_id: str, user_id: str) -> str:
    """Send today's questions for the workspace's first active standup. Returns what to tell the person."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.timezones import local_today  # noqa: PLC0415

    if db.can_administer(team_id, user_id, "standup") is not True:
        return "Only a workspace admin or a standup admin can send a standup early."
    schedules = sorted(
        (s for s in db.get_standup_schedules(team_id) if s.get("active")), key=lambda s: s.get("id") or 0
    )
    if not schedules:
        return "There is no active standup yet. Start one first, and add @Morgenruf to its channel."
    schedule = schedules[0]
    today = local_today(schedule.get("schedule_tz") or "UTC")
    if not db.claim_send_now(team_id, today):
        return "Today's questions were already sent early. Answers will show up in the channel."
    inst = db.get_installation(team_id) or {}
    token = inst.get("bot_token")
    if not token:
        db.release_send_now(team_id, today)
        return "I could not reach Slack for this workspace just now. Try again in a minute."
    from src.core.scheduler import _send_standup_to_workspace  # noqa: PLC0415

    try:
        _send_standup_to_workspace(
            team_id, token, schedule.get("channel_id") or "", int(schedule["id"]), skip_answered=True
        )
    except Exception:
        logger.exception("send it now failed for %s", team_id)
        db.release_send_now(team_id, today)
        return "I could not send the questions just now. Try again in a minute."
    name = schedule.get("name") or "your standup"
    return f"Sent. Everyone in *{name}* has today's questions in a DM now."


def available_rituals(team_id: str) -> list[tuple[str, str]]:
    """(name, label) for rituals this deployment offers that are not on yet."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.modules import deploy_allowlist, is_active_for  # noqa: PLC0415
    from src.modules import REGISTRY  # noqa: PLC0415

    allowlist = deploy_allowlist()
    out = []
    for spec in REGISTRY:
        if spec.name not in RITUALS or (allowlist is not None and spec.name not in allowlist):
            continue
        if is_active_for(team_id, spec.name) or not db.has_scopes(team_id, spec.required_scopes):
            continue
        out.append((spec.name, spec.nav[0].label if spec.nav else spec.name))
    return out


def rituals_modal(team_id: str) -> dict:
    options = available_rituals(team_id)
    if not options:
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Add a ritual"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Everything available is already on."}}],
        }
    return {
        "type": "modal",
        "callback_id": PICK_CALLBACK,
        "title": {"type": "plain_text", "text": "Add a ritual"},
        "submit": {"type": "plain_text", "text": "Turn on"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "rituals",
                "label": {"type": "plain_text", "text": "Turn on for the whole workspace"},
                "element": {
                    "type": "checkboxes",
                    "action_id": "rituals",
                    "options": [
                        {"text": {"type": "plain_text", "text": label}, "value": name} for name, label in options
                    ],
                },
            }
        ],
    }


def enable_rituals(team_id: str, user_id: str, names: list[str]) -> list[str]:
    """Turn on the chosen rituals. Workspace admins only. Returns what was turned on."""
    import src.core.db as db  # noqa: PLC0415

    if db.can_administer(team_id, user_id) is not True:
        return []
    allowed = {name for name, _ in available_rituals(team_id)}
    turned_on = [n for n in names if n in allowed]
    for name in turned_on:
        db.set_module_enabled(team_id, name, True)
    return turned_on


def invite_help_modal() -> dict:
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Add @Morgenruf"},
        "close": {"type": "plain_text", "text": "Got it"},
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": INVITE_HELP}}],
    }


def _ids(body: dict) -> tuple[str, str]:
    user = body.get("user") or {}
    team_id = (body.get("team") or {}).get("id") or user.get("team_id") or ""
    return team_id, user.get("id", "")


def _tell(client, user_id: str, text: str) -> None:  # noqa: ANN001
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception as exc:
        logger.info("activation: could not DM %s: %s", user_id, exc)


def register_slack(app) -> None:
    """The checklist and nudge buttons."""
    from src.core.home import refresh_home  # noqa: PLC0415

    @app.action(HIDE_ACTION)
    def handle_hide(ack, body, client):  # noqa: ANN001
        ack()
        import src.core.db as db  # noqa: PLC0415

        team_id, user_id = _ids(body)
        if db.can_administer(team_id, user_id) is not True:
            return
        try:
            db.hide_checklist(team_id, user_id)
        except Exception:
            logger.exception("activation: could not hide the checklist for %s", team_id)
            return
        refresh_home(team_id, user_id, client)

    @app.action(INVITE_HELP_ACTION)
    def handle_invite_help(ack, body, client):  # noqa: ANN001
        ack()
        try:
            client.views_open(trigger_id=body["trigger_id"], view=invite_help_modal())
        except Exception as exc:
            logger.info("activation: could not open the invite help: %s", exc)

    @app.action(SEND_NOW_ACTION)
    def handle_send_now(ack, body, client):  # noqa: ANN001
        ack()
        team_id, user_id = _ids(body)
        try:
            text = send_now(team_id, user_id)
        except Exception:
            logger.exception("activation: send it now failed in %s", team_id)
            text = "I could not send the questions just now. Try again in a minute."
        _tell(client, user_id, text)
        refresh_home(team_id, user_id, client)

    @app.action(PICK_ACTION)
    def handle_pick(ack, body, client):  # noqa: ANN001
        ack()
        import src.core.db as db  # noqa: PLC0415

        team_id, user_id = _ids(body)
        if db.can_administer(team_id, user_id) is not True:
            _tell(client, user_id, "Only a workspace admin can turn features on.")
            return
        try:
            client.views_open(trigger_id=body["trigger_id"], view=rituals_modal(team_id))
        except Exception as exc:
            logger.info("activation: could not open the ritual picker: %s", exc)

    @app.view(PICK_CALLBACK)
    def handle_pick_submit(ack, body, view, client):  # noqa: ANN001
        team_id, user_id = _ids(body)
        chosen = [
            o["value"]
            for o in ((view or {}).get("state", {}).get("values", {}).get("rituals", {}).get("rituals", {}) or {}).get(
                "selected_options"
            )
            or []
        ]
        turned_on = enable_rituals(team_id, user_id, chosen)
        if not turned_on:
            ack(response_action="errors", errors={"rituals": "Pick at least one, or ask a workspace admin."})
            return
        ack()
        refresh_home(team_id, user_id, client)

    @app.action(MEMBERS_ACTION)
    def handle_members(ack, body, client):  # noqa: ANN001
        ack()
        from src.core.dashboard_signin import signin_modal  # noqa: PLC0415

        team_id, user_id = _ids(body)
        try:
            client.views_open(trigger_id=body["trigger_id"], view=signin_modal(team_id, user_id))
        except Exception as exc:
            logger.info("activation: could not open the sign-in: %s", exc)


# ── Nudges ──────────────────────────────────────────────────────────────────


def _dm(row: dict, text: str, blocks: list[dict]) -> bool:
    try:
        client = WebClient(token=_bot_token(row["team_id"], row["bot_token"]))
        dm = client.conversations_open(users=row["installed_by_user_id"])["channel"]["id"]
        client.chat_postMessage(channel=dm, text=text, blocks=blocks)
        return True
    except Exception as exc:
        # Most often the workspace removed the app since the scan.
        logger.info("activation nudge not delivered for %s: %s", row.get("team_id"), exc)
        return False


def send_day2_nudges() -> tuple[int, int]:
    """DM each eligible installer once. Returns (sent, skipped)."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.quickstart_button import button_block  # noqa: PLC0415
    from src.core.usage_report import internal_teams  # noqa: PLC0415

    internal = internal_teams()
    sent = skipped = 0
    for row in db.workspaces_without_standup(hours=AFTER_HOURS):
        team_id = row["team_id"]
        user_id = row.get("installed_by_user_id")
        # The operator's own workspaces are not prospects.
        if team_id in internal:
            skipped += 1
            continue
        # Recorded before sending: a crash after this line loses one nudge,
        # it never sends two.
        if not user_id or not row.get("bot_token") or not db.record_install_email(team_id, KIND):
            skipped += 1
            continue
        try:
            client = WebClient(token=_bot_token(team_id, row["bot_token"]))
            dm = client.conversations_open(users=user_id)["channel"]["id"]
            client.chat_postMessage(
                channel=dm,
                text=TEXT,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": TEXT}}, button_block()],
            )
            sent += 1
        except Exception as exc:
            # Most often the workspace removed the app since the scan.
            logger.info("day-2 nudge not delivered for %s: %s", team_id, exc)
            skipped += 1
    if sent or skipped:
        logger.info("Day-2 nudges: %d sent, %d skipped", sent, skipped)
    return sent, skipped


DAY3_TEXT = "Your standup has not had an answer yet. Is @Morgenruf in the channel?"


def _day3_due(state: dict) -> bool:
    return bool(state.get("has_standup")) and int(state.get("responders") or 0) == 0


def _day7_message(all_steps: list[Step]) -> tuple[str, list[dict]]:
    done = sum(1 for s in all_steps if s.done)
    following = next(s for s in all_steps if not s.done)
    text = f"You are {done} of {len(all_steps)} in. Next: {following.title.lower()}."
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"You are *{done} of {len(all_steps)}* in."}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next: {following.title}*\n{following.hint}"},
            "accessory": _button(following),
        },
    ]
    return text, blocks


def _send_nudges(kind: str, hours: int, build) -> tuple[int, int]:  # noqa: ANN001
    """One DM per eligible installer for `kind`; `build(team_id)` returns (text, blocks) or None."""
    import src.core.db as db  # noqa: PLC0415
    from src.core.usage_report import internal_teams  # noqa: PLC0415

    internal = internal_teams()
    sent = skipped = 0
    for row in db.workspaces_for_activation_nudge(kind, hours):
        team_id = row["team_id"]
        if team_id in internal or not row.get("installed_by_user_id") or not row.get("bot_token"):
            skipped += 1
            continue
        try:
            message = build(team_id)
        except Exception:
            logger.exception("activation nudge %s could not be built for %s", kind, team_id)
            skipped += 1
            continue
        # Not due yet: nothing recorded, so a later pass can still send it.
        if message is None:
            skipped += 1
            continue
        if not db.record_install_email(team_id, kind):
            skipped += 1
            continue
        if _dm(row, *message):
            sent += 1
        else:
            skipped += 1
    if sent:
        logger.info("Activation nudges %s: %d sent, %d skipped", kind, sent, skipped)
    return sent, skipped


def send_day3_nudges() -> tuple[int, int]:
    """Day 3: a standup exists but nobody has answered. Offers Send it now."""
    import src.core.db as db  # noqa: PLC0415

    def build(team_id: str):  # noqa: ANN202
        if not _day3_due(db.checklist_state(team_id)):
            return None
        send = Step("answers", "", "", False, "Send it now", SEND_NOW_ACTION)
        return DAY3_TEXT, [
            {"type": "section", "text": {"type": "mrkdwn", "text": DAY3_TEXT}, "accessory": _button(send)}
        ]

    return _send_nudges(KIND_DAY3, DAY3_HOURS, build)


def send_day7_nudges() -> tuple[int, int]:
    """Day 7: fewer than three steps done. Names the next one, with its button."""

    def build(team_id: str):  # noqa: ANN202
        all_steps = steps_for(team_id)
        if sum(1 for s in all_steps if s.done) >= DAY7_BELOW:
            return None
        return _day7_message(all_steps)

    return _send_nudges(KIND_DAY7, DAY7_HOURS, build)


def send_activation_nudges() -> None:
    """Hourly: every nudge in order. One failing never stops the others."""
    for fn in (send_day2_nudges, send_day3_nudges, send_day7_nudges):
        try:
            fn()
        except Exception:
            logger.exception("activation nudge %s failed", getattr(fn, "__name__", fn))
