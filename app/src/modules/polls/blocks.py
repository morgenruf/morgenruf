"""What a poll looks like in Slack: the form, the message, the bars.

Everything a person typed is escaped here, at the one place it is shown, so a
question or option cannot ping a channel or disguise a link.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.modules.polls.parse import MAX_OPTION, MAX_OPTIONS, MAX_QUESTION

CREATE_CALLBACK = "polls:create"
OPEN_ACTION = "polls:open"

CLOSE_CHOICES = (
    ("never", "Never, I'll close it"),
    ("1h", "In 1 hour"),
    ("today", "At the end of today"),
    ("1d", "In 1 day"),
    ("1w", "In 1 week"),
)
CHECK_ANONYMOUS = "anonymous"
CHECK_MULTIPLE = "multiple"
CHECK_HIDE = "hide_results"

_NUMBERS = (":one:", ":two:", ":three:", ":four:", ":five:", ":six:", ":seven:", ":eight:", ":nine:", ":keycap_ten:")
_BAR_CELLS = 10
_VOTERS_SHOWN = 10


def escape(text: str) -> str:
    """Keep what a person typed as text, so `<!channel>` cannot ping anyone."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _plain(text: str) -> dict:
    return {"type": "plain_text", "text": text}


def _option(value: str, text: str) -> dict:
    return {"text": _plain(text), "value": value}


def create_modal(channel_id: str | None = None) -> dict:
    """The form behind `/morgenruf poll` and the App Home button."""
    channel = {
        "type": "conversations_select",
        "action_id": "polls:channel",
        "filter": {"include": ["public", "private"], "exclude_bot_users": True},
    }
    if channel_id and channel_id.startswith(("C", "G")):
        channel["initial_conversation"] = channel_id
    checks = [
        _option(CHECK_ANONYMOUS, "Anonymous"),
        _option(CHECK_MULTIPLE, "Allow more than one choice"),
        _option(CHECK_HIDE, "Hide results until the poll closes"),
    ]
    close = [_option(value, label) for value, label in CLOSE_CHOICES]
    return {
        "type": "modal",
        "callback_id": CREATE_CALLBACK,
        "title": _plain("Start a poll"),
        "submit": _plain("Post"),
        "close": _plain("Cancel"),
        "blocks": [
            {
                "type": "input",
                "block_id": "question",
                "label": _plain("Question"),
                "element": {
                    "type": "plain_text_input",
                    "action_id": "polls:question",
                    "max_length": MAX_QUESTION,
                    "placeholder": _plain("Where should we go for lunch?"),
                },
            },
            {
                "type": "input",
                "block_id": "options",
                "label": _plain("Options"),
                "hint": _plain(f"One per line, 2 to {MAX_OPTIONS}, each up to {MAX_OPTION} characters."),
                "element": {
                    "type": "plain_text_input",
                    "action_id": "polls:options",
                    "multiline": True,
                    "max_length": (MAX_OPTION + 1) * MAX_OPTIONS + 50,
                    "placeholder": _plain("Pizza\nSushi\nTacos"),
                },
            },
            {
                "type": "input",
                "block_id": "channel",
                "label": _plain("Post in"),
                "hint": _plain("Morgenruf has to be in the channel. Type /invite @Morgenruf there first."),
                "element": channel,
            },
            {
                "type": "input",
                "block_id": "settings",
                "optional": True,
                "label": _plain("Settings"),
                "element": {"type": "checkboxes", "action_id": "polls:settings", "options": checks},
            },
            {
                "type": "input",
                "block_id": "close",
                "label": _plain("Close"),
                "element": {
                    "type": "static_select",
                    "action_id": "polls:close_after",
                    "options": close,
                    "initial_option": close[0],
                },
            },
        ],
    }


def _bar(count: int, total: int) -> str:
    filled = round(_BAR_CELLS * count / total) if total else 0
    pct = round(100 * count / total) if total else 0
    return f"{'▓' * filled}{'░' * (_BAR_CELLS - filled)} {count} ({pct}%)"


def _voter_line(user_ids: list[str]) -> str:
    shown = " ".join(f"<@{u}>" for u in user_ids[:_VOTERS_SHOWN])
    extra = len(user_ids) - _VOTERS_SHOWN
    return f"{shown} +{extra}" if extra > 0 else shown


def _closes_text(closes_at) -> str:
    if not closes_at:
        return "Open until closed"
    if isinstance(closes_at, str):
        closes_at = datetime.fromisoformat(closes_at)
    if closes_at.tzinfo is None:
        closes_at = closes_at.replace(tzinfo=timezone.utc)
    fallback = closes_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Closes <!date^{int(closes_at.timestamp())}^{{date_short_pretty}} at {{time}}|{fallback}>"


def _context(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def fallback_text(poll: dict) -> str:
    return f"Poll: {escape(poll.get('question', ''))}"


def poll_message(poll: dict, counts: list[int], voters_by_option: dict[int, list[str]] | None, closed: bool) -> list:
    """The poll as Slack blocks.

    While a poll hides its results, the message carries only the total, never
    a count per option. Voter mentions appear only on a named poll; for an
    anonymous one the caller passes none and none are shown.
    """
    poll_id = poll["id"]
    options = list(poll.get("options") or [])
    counts = list(counts or []) + [0] * (len(options) - len(counts or []))
    total = sum(counts)
    show_counts = closed or not poll.get("hide_results")
    names = {} if poll.get("anonymous") else (voters_by_option or {})

    blocks: list[dict] = [{"type": "section", "text": {"type": "mrkdwn", "text": f"*{escape(poll['question'])}*"}}]
    for idx, text in enumerate(options):
        number = _NUMBERS[idx] if idx < len(_NUMBERS) else f"{idx + 1}."
        section = {"type": "section", "text": {"type": "mrkdwn", "text": f"{number} {escape(text)}"}}
        if not closed:
            section["accessory"] = {
                "type": "button",
                "text": _plain("Vote"),
                "action_id": f"polls:vote:{poll_id}:{idx}",
                "value": str(idx),
            }
        blocks.append(section)
        if show_counts:
            line = _bar(counts[idx], total)
            voters = names.get(idx) or []
            if voters:
                line = f"{line}  {_voter_line(voters)}"
            blocks.append(_context(line))

    if not show_counts:
        noun = "vote" if total == 1 else "votes"
        blocks.append(_context(f"{total} {noun} so far. Results show when the poll closes."))

    footer = [
        "Anonymous" if poll.get("anonymous") else "Named",
        "Multiple choice" if poll.get("multiple") else "One choice",
        "Closed" if closed else _closes_text(poll.get("closes_at")),
        f"Started by <@{poll['created_by']}>",
    ]
    blocks.append(_context(" · ".join(footer)))

    if not closed:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": _plain("Close poll"),
                        "action_id": f"polls:close:{poll_id}",
                        "value": str(poll_id),
                        "style": "danger",
                        "confirm": {
                            "title": _plain("Close this poll?"),
                            "text": _plain("Nobody can vote after this, and the results are shown to everyone."),
                            "confirm": _plain("Close it"),
                            "deny": _plain("Keep it open"),
                        },
                    }
                ],
            }
        )
    return blocks
