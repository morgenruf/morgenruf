"""What the pulse DM looks like. Buttons only: there is no free text in pulse."""

from __future__ import annotations

from src.modules.pulse import questions

INTRO = (
    "Weekly check-in. Two taps, anonymous: your answer is stored without your name, "
    "and results only show as a team average once at least 5 people answer."
)
THANKS = "Thanks, noted."
CLOSED = "This check-in has closed."
TURNED_OFF = "The weekly check-in is turned off in this workspace, so nothing was recorded."
REMINDER = "Reminder: this week's check-in closes tomorrow. Scroll up to the questions; it takes two taps."

_MOOD_EMOJI = ("😣", "😕", "😐", "🙂", "😄")


def _plain(text: str) -> dict:
    return {"type": "plain_text", "text": text, "emoji": True}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _button(round_id: int, key: str, value: int, label: str) -> dict:
    return {
        "type": "button",
        "text": _plain(label),
        "action_id": f"pulse:answer:{round_id}:{key}:{value}",
        "value": str(value),
    }


def mood_question(round_id: int, intro: bool = True) -> list[dict]:
    blocks = [_section(INTRO)] if intro else []
    blocks.append(_section(f"*{questions.MOOD_TEXT}*"))
    blocks.append(
        {
            "type": "actions",
            "elements": [
                _button(round_id, questions.MOOD, v, f"{_MOOD_EMOJI[v - 1]} {label}")
                for v, label in zip(questions.values(questions.MOOD), questions.MOOD_LABELS)
            ],
        }
    )
    return blocks


def enps_question(round_id: int) -> list[dict]:
    values = list(questions.values(questions.ENPS))
    return [
        _section(f"*{questions.ENPS_TEXT}*"),
        {"type": "actions", "elements": [_button(round_id, questions.ENPS, v, str(v)) for v in values[:6]]},
        {"type": "actions", "elements": [_button(round_id, questions.ENPS, v, str(v)) for v in values[6:]]},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "0 is not at all likely, 10 is extremely likely."}],
        },
    ]


def question(round_id: int, key: str) -> list[dict]:
    return enps_question(round_id) if key == questions.ENPS else mood_question(round_id, intro=False)


def note(text: str) -> list[dict]:
    """What replaces the buttons once they are used. Never the value picked."""
    return [
        _section(text),
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Your answer is stored without your name."}],
        },
    ]
