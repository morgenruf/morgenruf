"""What Watercooler says: the channel post, its DMs, the setup modal, the Home section."""

from __future__ import annotations

from src.modules.watercooler import bank

OPEN_ACTION = "watercooler:open"
SETUP_CALLBACK = "watercooler:setup"
CHANNEL_ACTION = "watercooler:channel"
DAYS_ACTION = "watercooler:days"
TIME_ACTION = "watercooler:time"
REACTION = "raising_hand"
DAY_OPTIONS = (
    ("mon", "Mon"),
    ("tue", "Tue"),
    ("wed", "Wed"),
    ("thu", "Thu"),
    ("fri", "Fri"),
    ("sat", "Sat"),
    ("sun", "Sun"),
)


def escape(text: str) -> str:
    """A question is shown as text: no mentions, links or channel pings from a custom one."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def post_text(question: str) -> str:
    return f"☕ Watercooler: {question}"


def post_blocks(question: str) -> list[dict]:
    return [
        {"type": "header", "text": {"type": "plain_text", "text": "☕ Watercooler", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{escape(question)}*"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "Reply in the thread 👇"}]},
    ]


def not_in_channel_text(channel_id: str) -> str:
    return (
        f"☕ I couldn't post today's watercooler question in <#{channel_id}> because I'm not in that channel, "
        "so I've paused it. Add me from the channel: open the channel details, then *Integrations*, "
        "then *Add apps*, and pick Morgenruf. Then press *Resume* on the Watercooler page of the dashboard "
        "or set the channel up again with `/morgenruf watercooler`."
    )


def empty_pool_text(channel_id: str) -> str:
    return (
        f"☕ <#{channel_id}> has no watercooler questions left to ask: every question it may use is hidden "
        "or archived. Add a question or turn some back on from the Watercooler page of the dashboard."
    )


def saved_text(channel_id: str, days: str, post_time: str, tz: str) -> str:
    labels = dict(DAY_OPTIONS)
    when = ", ".join(labels.get(d, d) for d in days.split(",") if d)
    return f"☕ Watercooler is set for <#{channel_id}>: {when} at {post_time} ({tz}). Reply in the thread to join in."


def setup_modal(tz: str, channel_id: str = "", days: str = "mon,wed,fri", post_time: str = "10:00") -> dict:
    day_opts = [{"text": {"type": "plain_text", "text": label}, "value": key} for key, label in DAY_OPTIONS]
    chosen = set(days.split(","))
    channel_element: dict = {
        "type": "conversations_select",
        "action_id": CHANNEL_ACTION,
        "filter": {"include": ["public", "private"], "exclude_bot_users": True},
    }
    if channel_id:
        channel_element["initial_conversation"] = channel_id
    return {
        "type": "modal",
        "callback_id": SETUP_CALLBACK,
        "title": {"type": "plain_text", "text": "Watercooler"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": tz,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "A conversation question in a channel on the days you pick. People reply in the thread.",
                },
            },
            {
                "type": "input",
                "block_id": "channel",
                "label": {"type": "plain_text", "text": "Channel"},
                "element": channel_element,
            },
            {
                "type": "input",
                "block_id": "days",
                "label": {"type": "plain_text", "text": "Days"},
                "element": {
                    "type": "checkboxes",
                    "action_id": DAYS_ACTION,
                    "options": day_opts,
                    "initial_options": [o for o in day_opts if o["value"] in chosen],
                },
            },
            {
                "type": "input",
                "block_id": "time",
                "label": {"type": "plain_text", "text": "Time"},
                "element": {"type": "timepicker", "action_id": TIME_ACTION, "initial_time": post_time},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Times are in {tz}. Nothing posts on company holidays or days off. "
                            "Pick question categories, hide questions or add your own in the dashboard."
                        ),
                    }
                ],
            },
        ],
    }


def home_blocks(channels: list[dict], can_set_up: bool) -> list[dict]:
    blocks: list[dict] = [{"type": "divider"}]
    section: dict = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*☕ Watercooler*\nA conversation question in a channel, a few times a week.",
        },
    }
    if can_set_up:
        section["accessory"] = {
            "type": "button",
            "text": {"type": "plain_text", "text": "Start watercooler" if not channels else "Add a channel"},
            "action_id": OPEN_ACTION,
        }
    blocks.append(section)
    if channels:
        lines = []
        for ch in channels:
            state = "" if ch.get("active", True) else "  (paused)"
            lines.append(f"• <#{ch['channel_id']}>  {ch.get('days', '')} at {ch.get('post_time', '')}{state}")
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "\n".join(lines)}]})
    return blocks


def category_label(key: str) -> str:
    return bank.CATEGORY_LABELS.get(key, key)
