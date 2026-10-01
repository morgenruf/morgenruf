"""Pulse in Slack: the answer buttons, `/morgenruf pulse`, and the App Home.

An answer is acknowledged by replacing the buttons with "Thanks, noted.", and
never by echoing what was picked: someone looking over a shoulder, or at a
screenshot, sees nothing. Logs carry counts and round ids, never a user id
next to a value.
"""

from __future__ import annotations

import logging
import re

from src.modules.pulse import blocks as pblocks
from src.modules.pulse import questions

logger = logging.getLogger(__name__)

MODULE_NAME = "pulse"

_ANSWER = re.compile(r"^pulse:answer:(\d+):([a-z]+):(\d+)$")
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _team_id(body: dict) -> str:
    return (body.get("team") or {}).get("id") or (body.get("user") or {}).get("team_id", "")


def _is_admin(team_id: str, user_id: str) -> bool:
    try:
        import src.core.db as db  # noqa: PLC0415

        return db.can_administer(team_id, user_id, MODULE_NAME)
    except Exception:
        return False


def _schedule_text(program: dict) -> str:
    day = _DAYS[int(program.get("day_of_week") or 0) % 7]
    return f"{day}s at {int(program.get('hour') or 0):02d}:{int(program.get('minute') or 0):02d} {program.get('timezone') or 'UTC'}"


def _pulse_url() -> str:
    from src.core.links import dashboard_url  # noqa: PLC0415

    return f"{dashboard_url().rstrip('/')}/pulse"


def handle_answer(ack, body, client) -> None:  # noqa: ANN001
    ack()
    import src.modules.pulse.db as pdb  # noqa: PLC0415
    from src.core.modules import is_active_for  # noqa: PLC0415

    action = (body.get("actions") or [{}])[0]
    match = _ANSWER.match(action.get("action_id", ""))
    if not match:
        return
    round_id, key, value = int(match.group(1)), match.group(2), int(match.group(3))
    user_id = (body.get("user") or {}).get("id", "")
    team_id = _team_id(body)
    channel_id = (body.get("channel") or {}).get("id") or (body.get("container") or {}).get("channel_id", "")
    ts = (body.get("container") or {}).get("message_ts") or (body.get("message") or {}).get("ts")

    def replace(text: str) -> None:
        try:
            client.chat_update(channel=channel_id, ts=ts, text=text, blocks=pblocks.note(text))
        except Exception as exc:
            logger.info("pulse: could not replace the buttons on round %s: %s", round_id, exc)

    round_ = pdb.get_round(round_id)
    if not round_ or round_.get("team_id") != team_id or round_.get("closed"):
        replace(pblocks.CLOSED)
        return
    if not is_active_for(team_id, MODULE_NAME):
        replace(pblocks.TURNED_OFF)
        return
    try:
        counted = pdb.record_answer(round_id, user_id, key, value)
    except Exception:
        logger.exception("pulse: could not record an answer on round %s", round_id)
        return
    replace(pblocks.THANKS)
    if not counted:
        return

    remaining = [q for q in questions.round_questions(round_.get("includes_enps")) if q != key]
    try:
        done = pdb.answered(round_id, user_id)
    except Exception:
        done = {key}
    nxt = next((q for q in remaining if q not in done), None)
    if nxt is None:
        return
    try:
        client.chat_postMessage(channel=user_id, text=pblocks.INTRO, blocks=pblocks.question(round_id, nxt))
    except Exception as exc:
        logger.info("pulse: could not send the next question on round %s: %s", round_id, exc)


def handle_pulse_command(body: dict, client, respond, args_text: str) -> None:  # noqa: ANN001
    """`/morgenruf pulse`: what it is, that it is anonymous, and whether it is on."""
    import src.modules.pulse.db as pdb  # noqa: PLC0415
    from src.modules.pulse.privacy import MIN_GROUP  # noqa: PLC0415

    team_id = body.get("team_id", "")
    user_id = body.get("user_id", "")
    try:
        program = pdb.get_program(team_id)
    except Exception as exc:
        logger.warning("pulse: could not read the programme for %s: %s", team_id, exc)
        program = None

    lines = [
        "*Pulse* is a weekly check-in by DM: how work was this week on a 1 to 5 scale, "
        "and every fourth week how likely you are to recommend working here.",
        f"Answers are anonymous. Each one is stored without your name, and results only show as "
        f"team averages once at least {MIN_GROUP} people answer. Nobody, admins included, can see "
        "what one person said.",
    ]
    if program is None:
        lines.append("I couldn't check whether it is on just now.")
    elif program.get("enabled"):
        lines.append(f"It is on here: the next check-in arrives {_schedule_text(program)}.")
    else:
        lines.append("It is off in this workspace right now.")
    if _is_admin(team_id, user_id):
        lines.append(f"You can change it on the <{_pulse_url()}|Pulse page in the dashboard>.")

    text = "\n\n".join(lines)
    try:
        if respond is not None:
            respond(text=text, response_type="ephemeral")
            return
    except Exception:
        logger.info("pulse: respond failed, sending a DM instead")
    try:
        client.chat_postMessage(channel=user_id, text=text)
    except Exception:
        logger.info("pulse: could not answer /morgenruf pulse")


def home_blocks(team_id: str, user_id: str) -> list[dict]:
    """Admins see the state and schedule; members, one line when it is on."""
    import src.modules.pulse.db as pdb  # noqa: PLC0415

    try:
        program = pdb.get_program(team_id)
    except Exception as exc:
        logger.warning("pulse App Home unavailable for %s: %s", team_id, exc)
        return []
    if _is_admin(team_id, user_id):
        state = (
            f"Weekly check-in is *on*. Next round: {_schedule_text(program)}."
            if program.get("enabled")
            else "Weekly check-in is *off*."
        )
        text = f"*💬 Pulse*\n{state}\n<{_pulse_url()}|Settings and team trends in the dashboard>"
    elif program.get("enabled"):
        text = "*💬 Pulse*\nWeekly check-in is on. Answers are anonymous."
    else:
        return []
    return [{"type": "divider"}, {"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def register_handlers(app) -> None:
    """The answer buttons. The command is a `/morgenruf` subcommand."""
    app.action(re.compile(r"^pulse:answer:"))(handle_answer)
