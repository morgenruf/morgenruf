"""Slack Block Kit JSON builders for Morgenruf."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _time_options() -> list[dict]:
    """96 options — 00:00 to 23:45 in 15-minute increments."""
    options = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            label = f"{h:02d}:{m:02d}"
            options.append({"text": {"type": "plain_text", "text": label}, "value": label})
    return options


_TIMEZONE_ZONES = [
    ("UTC", "UTC"),
    ("America/New_York", "America/New_York (ET)"),
    ("America/Chicago", "America/Chicago (CT)"),
    ("America/Denver", "America/Denver (MT)"),
    ("America/Los_Angeles", "America/Los_Angeles (PT)"),
    ("America/Toronto", "America/Toronto (ET)"),
    ("America/Vancouver", "America/Vancouver (PT)"),
    ("America/Phoenix", "America/Phoenix (AZ)"),
    ("America/Anchorage", "America/Anchorage (AKT)"),
    ("Pacific/Honolulu", "Pacific/Honolulu (HST)"),
    ("America/Sao_Paulo", "America/Sao_Paulo (BRT)"),
    ("America/Argentina/Buenos_Aires", "America/Argentina/Buenos_Aires (ART)"),
    ("America/Bogota", "America/Bogota (COT)"),
    ("America/Lima", "America/Lima (PET)"),
    ("America/Mexico_City", "America/Mexico_City (CST)"),
    ("Europe/London", "Europe/London (GMT/BST)"),
    ("Europe/Dublin", "Europe/Dublin (IST)"),
    ("Europe/Paris", "Europe/Paris (CET)"),
    ("Europe/Berlin", "Europe/Berlin (CET)"),
    ("Europe/Amsterdam", "Europe/Amsterdam (CET)"),
    ("Europe/Madrid", "Europe/Madrid (CET)"),
    ("Europe/Rome", "Europe/Rome (CET)"),
    ("Europe/Warsaw", "Europe/Warsaw (CET)"),
    ("Europe/Stockholm", "Europe/Stockholm (CET)"),
    ("Europe/Zurich", "Europe/Zurich (CET)"),
    ("Europe/Oslo", "Europe/Oslo (CET)"),
    ("Europe/Helsinki", "Europe/Helsinki (EET)"),
    ("Europe/Athens", "Europe/Athens (EET)"),
    ("Europe/Bucharest", "Europe/Bucharest (EET)"),
    ("Europe/Istanbul", "Europe/Istanbul (TRT)"),
    ("Europe/Moscow", "Europe/Moscow (MSK)"),
    ("Africa/Cairo", "Africa/Cairo (EET)"),
    ("Africa/Johannesburg", "Africa/Johannesburg (SAST)"),
    ("Africa/Lagos", "Africa/Lagos (WAT)"),
    ("Africa/Nairobi", "Africa/Nairobi (EAT)"),
    ("Asia/Dubai", "Asia/Dubai (GST)"),
    ("Asia/Kolkata", "Asia/Kolkata (IST)"),
    ("Asia/Colombo", "Asia/Colombo (SLST)"),
    ("Asia/Dhaka", "Asia/Dhaka (BST)"),
    ("Asia/Kathmandu", "Asia/Kathmandu (NPT)"),
    ("Asia/Karachi", "Asia/Karachi (PKT)"),
    ("Asia/Tashkent", "Asia/Tashkent (UZT)"),
    ("Asia/Almaty", "Asia/Almaty (ALMT)"),
    ("Asia/Bangkok", "Asia/Bangkok (ICT)"),
    ("Asia/Jakarta", "Asia/Jakarta (WIB)"),
    ("Asia/Singapore", "Asia/Singapore (SGT)"),
    ("Asia/Kuala_Lumpur", "Asia/Kuala_Lumpur (MYT)"),
    ("Asia/Shanghai", "Asia/Shanghai (CST)"),
    ("Asia/Hong_Kong", "Asia/Hong_Kong (HKT)"),
    ("Asia/Taipei", "Asia/Taipei (CST)"),
    ("Asia/Seoul", "Asia/Seoul (KST)"),
    ("Asia/Tokyo", "Asia/Tokyo (JST)"),
    ("Asia/Yakutsk", "Asia/Yakutsk (YAKT)"),
    ("Asia/Vladivostok", "Asia/Vladivostok (VLAT)"),
    ("Australia/Perth", "Australia/Perth (AWST)"),
    ("Australia/Darwin", "Australia/Darwin (ACST)"),
    ("Australia/Adelaide", "Australia/Adelaide (ACST/ACDT)"),
    ("Australia/Brisbane", "Australia/Brisbane (AEST)"),
    ("Australia/Sydney", "Australia/Sydney (AEST/AEDT)"),
    ("Australia/Melbourne", "Australia/Melbourne (AEST/AEDT)"),
    ("Pacific/Auckland", "Pacific/Auckland (NZST/NZDT)"),
    ("Pacific/Fiji", "Pacific/Fiji (FJT)"),
    ("Pacific/Guam", "Pacific/Guam (ChST)"),
]

_TZ_ALIASES: dict[str, str] = {
    "calcutta": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
    "bombay": "Asia/Kolkata", "mumbai": "Asia/Kolkata",
    "madras": "Asia/Chennai", "chennai": "Asia/Chennai",
    "ist": "Asia/Kolkata", "pst": "America/Los_Angeles",
    "est": "America/New_York", "cst": "America/Chicago",
    "mst": "America/Denver", "gmt": "Europe/London",
    "bst": "Europe/London", "cet": "Europe/Paris",
    "jst": "Asia/Tokyo", "kst": "Asia/Seoul",
    "aest": "Australia/Sydney", "nzst": "Pacific/Auckland",
    "india": "Asia/Kolkata", "japan": "Asia/Tokyo",
    "china": "Asia/Shanghai", "korea": "Asia/Seoul",
}


def _timezone_options() -> list[dict]:
    return [{"text": {"type": "plain_text", "text": label}, "value": value} for value, label in _TIMEZONE_ZONES]


def timezone_search(query: str) -> list[dict]:
    """Search timezones by substring and alias. Returns Slack option dicts."""
    all_opts = _timezone_options()
    q = (query or "").lower().strip()
    if not q:
        return all_opts

    # Substring match on label (case-insensitive)
    matches = [opt for opt in all_opts if q in opt["text"]["text"].lower()]

    # Alias match — add to top if not already present
    matched_values = {opt["value"] for opt in matches}
    alias_hit = _TZ_ALIASES.get(q)
    if not alias_hit:
        # Partial alias match
        for alias_key, tz_value in _TZ_ALIASES.items():
            if q in alias_key:
                alias_hit = tz_value
                break
    if alias_hit and alias_hit not in matched_values:
        alias_opt = _find_option(all_opts, alias_hit)
        if alias_opt:
            matches.insert(0, alias_opt)

    return matches[:100]


# ---------------------------------------------------------------------------
# Rich-text ↔ mrkdwn conversion
# ---------------------------------------------------------------------------


def _rt_elements_to_mrkdwn(elements: list[dict]) -> str:
    """Convert rich_text element list (text, link, user, etc.) to mrkdwn."""
    parts: list[str] = []
    for el in elements:
        el_type = el.get("type", "")
        if el_type == "text":
            text = el.get("text", "")
            style = el.get("style", {})
            if style.get("code"):
                text = f"`{text}`"
            if style.get("bold"):
                text = f"*{text}*"
            if style.get("italic"):
                text = f"_{text}_"
            if style.get("strike"):
                text = f"~{text}~"
            parts.append(text)
        elif el_type == "link":
            url = el.get("url", "")
            text = el.get("text", url)
            parts.append(f"<{url}|{text}>" if text != url else url)
        elif el_type == "user":
            parts.append(f"<@{el.get('user_id', '')}>")
        elif el_type == "channel":
            parts.append(f"<#{el.get('channel_id', '')}>")
        elif el_type == "emoji":
            parts.append(f":{el.get('name', '')}:")
    return "".join(parts)


def rich_text_to_mrkdwn(rich_text: dict) -> str:
    """Convert a Slack rich_text block value to a mrkdwn string."""
    if not rich_text or not isinstance(rich_text, dict):
        return ""
    parts: list[str] = []
    for block in rich_text.get("elements", []):
        btype = block.get("type", "")
        if btype == "rich_text_section":
            parts.append(_rt_elements_to_mrkdwn(block.get("elements", [])))
        elif btype == "rich_text_list":
            style = block.get("style", "bullet")
            indent = block.get("indent", 0)
            prefix_pad = "    " * indent
            items: list[str] = []
            for idx, item in enumerate(block.get("elements", [])):
                prefix = f"{prefix_pad}• " if style == "bullet" else f"{prefix_pad}{idx + 1}. "
                items.append(prefix + _rt_elements_to_mrkdwn(item.get("elements", [])))
            parts.append("\n".join(items))
        elif btype == "rich_text_preformatted":
            parts.append("```\n" + _rt_elements_to_mrkdwn(block.get("elements", [])) + "\n```")
        elif btype == "rich_text_quote":
            lines = _rt_elements_to_mrkdwn(block.get("elements", [])).split("\n")
            parts.append("\n".join("> " + line for line in lines))
    return "\n".join(parts)


def mrkdwn_to_rich_text(text: str) -> dict:
    """Wrap a plain/mrkdwn string as a rich_text block for initial_value."""
    return {
        "type": "rich_text",
        "elements": [
            {"type": "rich_text_section", "elements": [{"type": "text", "text": text}]}
        ],
    }


def _reminder_options() -> list[dict]:
    return [
        {"text": {"type": "plain_text", "text": "No reminder"}, "value": "0"},
        {"text": {"type": "plain_text", "text": "15 minutes before"}, "value": "15"},
        {"text": {"type": "plain_text", "text": "30 minutes before"}, "value": "30"},
        {"text": {"type": "plain_text", "text": "1 hour before"}, "value": "60"},
        {"text": {"type": "plain_text", "text": "2 hours before"}, "value": "120"},
    ]


def _day_options() -> list[dict]:
    return [
        {"text": {"type": "plain_text", "text": "Mon"}, "value": "mon"},
        {"text": {"type": "plain_text", "text": "Tue"}, "value": "tue"},
        {"text": {"type": "plain_text", "text": "Wed"}, "value": "wed"},
        {"text": {"type": "plain_text", "text": "Thu"}, "value": "thu"},
        {"text": {"type": "plain_text", "text": "Fri"}, "value": "fri"},
        {"text": {"type": "plain_text", "text": "Sat"}, "value": "sat"},
        {"text": {"type": "plain_text", "text": "Sun"}, "value": "sun"},
    ]


def _find_option(options: list[dict], value: str) -> dict | None:
    for opt in options:
        if opt["value"] == value:
            return opt
    return None


# ---------------------------------------------------------------------------
# Modal: Create / Edit standup
# ---------------------------------------------------------------------------


def create_standup_modal(existing_config: dict | None = None, bot_channels: list[dict] | None = None) -> dict:
    """
    Full 'Create a standup' modal matching Standup & Prosper UX.
    Pass existing_config to pre-fill fields when editing.
    bot_channels: list of {"id": ..., "name": ...} dicts for channels the bot is in.
    """
    cfg = existing_config or {}
    is_edit = bool(cfg.get("standup_id"))

    default_questions = "What did you do yesterday?\nWhat will you do today?\nAny blockers?"
    questions_text = "\n".join(cfg.get("questions", [])) if cfg.get("questions") else default_questions

    time_options = _time_options()
    tz_options = _timezone_options()
    reminder_options = _reminder_options()
    day_options = _day_options()

    selected_time = _find_option(time_options, cfg.get("report_time", "09:00")) or time_options[36]
    tz_value = cfg.get("timezone", "UTC")
    selected_tz = _find_option(tz_options, tz_value) or tz_options[0]
    selected_reminder = _find_option(reminder_options, str(cfg.get("reminder_minutes", 60))) or reminder_options[3]

    active_days = cfg.get("days", ["mon", "tue", "wed", "thu", "fri"])
    initial_days = [opt for opt in day_options if opt["value"] in active_days]

    report_dest_options = [
        {"text": {"type": "plain_text", "text": "Directly to the channel"}, "value": "channel"},
        {"text": {"type": "plain_text", "text": "As a thread reply"}, "value": "thread"},
    ]
    selected_dest = (
        _find_option(report_dest_options, cfg.get("report_destination", "channel")) or report_dest_options[0]
    )

    group_by_options = [
        {"text": {"type": "plain_text", "text": "Team Member"}, "value": "member"},
        {"text": {"type": "plain_text", "text": "Question"}, "value": "question"},
    ]
    selected_group = _find_option(group_by_options, cfg.get("group_by", "member")) or group_by_options[0]

    # Build channel options from bot-joined channels
    channel_opts = [
        {"text": {"type": "plain_text", "text": c["name"]}, "value": c["id"]}
        for c in sorted(bot_channels or [], key=lambda c: c["name"])
    ]
    channel_element: dict = {
        "type": "static_select",
        "action_id": "standup_channel",
        "placeholder": {"type": "plain_text", "text": "Select a channel"},
        "options": channel_opts
        or [{"text": {"type": "plain_text", "text": "No channels — invite the bot first"}, "value": "_none"}],
    }
    if cfg.get("channel_id") and channel_opts:
        initial = _find_option(channel_opts, cfg["channel_id"])
        if initial:
            channel_element["initial_option"] = initial

    blocks = [
        # Channel
        {
            "type": "input",
            "block_id": "standup_channel",
            "label": {"type": "plain_text", "text": "Standup channel"},
            "element": channel_element,
        },
        # Questions
        {
            "type": "input",
            "block_id": "questions",
            "label": {"type": "plain_text", "text": "Standup questions"},
            "hint": {"type": "plain_text", "text": "One question per line (up to 10)"},
            "element": {
                "type": "plain_text_input",
                "action_id": "questions",
                "multiline": True,
                "initial_value": questions_text,
                "placeholder": {
                    "type": "plain_text",
                    "text": "What did you do yesterday?\nWhat will you do today?\nAny blockers?",
                },
            },
        },
        # Report time
        {
            "type": "input",
            "block_id": "report_time",
            "label": {"type": "plain_text", "text": "Report time"},
            "element": {
                "type": "static_select",
                "action_id": "report_time",
                "options": time_options,
                "initial_option": selected_time,
            },
        },
        # Timezone
        {
            "type": "input",
            "block_id": "timezone",
            "label": {"type": "plain_text", "text": "Timezone"},
            "element": {
                "type": "external_select",
                "action_id": "timezone",
                "min_query_length": 0,
                "placeholder": {"type": "plain_text", "text": "Search timezone..."},
                **({"initial_option": selected_tz} if selected_tz else {}),
            },
        },
        # Reminder
        {
            "type": "input",
            "block_id": "reminder",
            "label": {"type": "plain_text", "text": "Send reminder"},
            "element": {
                "type": "static_select",
                "action_id": "reminder",
                "options": reminder_options,
                "initial_option": selected_reminder,
            },
        },
        # Members
        {
            "type": "input",
            "block_id": "members",
            "label": {"type": "plain_text", "text": "Standup members"},
            "element": {
                "type": "multi_users_select",
                "action_id": "members",
                "placeholder": {"type": "plain_text", "text": "Select team members"},
                **({"initial_users": cfg["members"]} if cfg.get("members") else {}),
            },
        },
        # Sync with channel
        {
            "type": "input",
            "block_id": "sync_channel",
            "label": {"type": "plain_text", "text": "Channel sync"},
            "optional": True,
            "element": {
                "type": "checkboxes",
                "action_id": "sync_channel",
                "options": [
                    {
                        "text": {
                            "type": "mrkdwn",
                            "text": "Automatically add and remove standup members based on channel membership",
                        },
                        "value": "sync",
                    }
                ],
                **(
                    {
                        "initial_options": [
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "Automatically add and remove standup members based on channel membership",
                                },
                                "value": "sync",
                            }
                        ]
                    }
                    if cfg.get("sync_with_channel")
                    else {}
                ),
            },
        },
        # Days
        {
            "type": "input",
            "block_id": "days",
            "label": {"type": "plain_text", "text": "Active days"},
            "element": {
                "type": "checkboxes",
                "action_id": "days",
                "options": day_options,
                **({"initial_options": initial_days} if initial_days else {}),
            },
        },
        # Report destination
        {
            "type": "input",
            "block_id": "report_destination",
            "label": {"type": "plain_text", "text": "Post report"},
            "element": {
                "type": "static_select",
                "action_id": "report_destination",
                "options": report_dest_options,
                "initial_option": selected_dest,
            },
        },
        # Group by
        {
            "type": "input",
            "block_id": "group_by",
            "label": {"type": "plain_text", "text": "Group report by"},
            "element": {
                "type": "static_select",
                "action_id": "group_by",
                "options": group_by_options,
                "initial_option": selected_group,
            },
        },
        # Standup name (optional)
        {
            "type": "input",
            "block_id": "standup_name",
            "label": {"type": "plain_text", "text": "Standup name"},
            "optional": True,
            "element": {
                "type": "plain_text_input",
                "action_id": "standup_name",
                "placeholder": {"type": "plain_text", "text": "Team Standup"},
                **({"initial_value": cfg["standup_name"]} if cfg.get("standup_name") else {}),
            },
        },
        # Answer prepopulation
        {
            "type": "input",
            "block_id": "prepopulate_answers",
            "label": {"type": "plain_text", "text": "Answer prepopulation"},
            "optional": True,
            "element": {
                "type": "checkboxes",
                "action_id": "prepopulate_answers",
                "options": [
                    {
                        "text": {
                            "type": "mrkdwn",
                            "text": "Pre-fill standup form with each member's previous answers",
                        },
                        "value": "prepopulate",
                    }
                ],
                **(
                    {
                        "initial_options": [
                            {
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "Pre-fill standup form with each member's previous answers",
                                },
                                "value": "prepopulate",
                            }
                        ]
                    }
                    if cfg.get("prepopulate_answers")
                    else {}
                ),
            },
        },
    ]

    # Edit-only fields
    if is_edit:
        _prepop_text = "Allow members to edit responses after the report is posted"
        blocks.append(
            {
                "type": "input",
                "block_id": "allow_edit_after_report",
                "label": {"type": "plain_text", "text": "Edit window"},
                "optional": True,
                "element": {
                    "type": "checkboxes",
                    "action_id": "allow_edit_after_report",
                    "options": [{"text": {"type": "mrkdwn", "text": _prepop_text}, "value": "allow"}],
                    **(
                        {"initial_options": [{"text": {"type": "mrkdwn", "text": _prepop_text}, "value": "allow"}]}
                        if cfg.get("allow_edit_after_report")
                        else {}
                    ),
                },
            }
        )
        active_options = [
            {"text": {"type": "plain_text", "text": "Enabled"}, "value": "true"},
            {"text": {"type": "plain_text", "text": "Disabled"}, "value": "false"},
        ]
        current_active = "true" if cfg.get("active", True) else "false"
        blocks.append(
            {
                "type": "input",
                "block_id": "standup_active",
                "label": {"type": "plain_text", "text": "Enable the standup"},
                "element": {
                    "type": "static_select",
                    "action_id": "standup_active",
                    "options": active_options,
                    "initial_option": _find_option(active_options, current_active),
                },
            }
        )

    modal: dict = {
        "type": "modal",
        "callback_id": "create_standup_modal",
        "title": {
            "type": "plain_text",
            "text": "Edit standup" if is_edit else "Create a standup",
        },
        "submit": {"type": "plain_text", "text": "Save" if is_edit else "Create"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }

    if is_edit:
        modal["private_metadata"] = cfg.get("standup_id", "")

    return modal


# ---------------------------------------------------------------------------
# DM: Standup prompt sent to user at standup time
# ---------------------------------------------------------------------------


def standup_dm_message(questions: list[str], standup_name: str) -> dict:
    """DM message sent to user when it is standup time."""
    first_question = questions[0] if questions else "What did you do yesterday?"
    return {
        "blocks": [
            {
                "type": "header",
                "block_id": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🌅 Time for your standup! — {standup_name}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "block_id": "first_question",
                "text": {"type": "mrkdwn", "text": f"*{first_question}*"},
            },
            {
                "type": "actions",
                "block_id": "standup_actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "fill_in_form",
                        "text": {"type": "plain_text", "text": "Fill in form", "emoji": True},
                        "style": "primary",
                        "value": "fill_in_form",
                    },
                    {
                        "type": "button",
                        "action_id": "skip_standup",
                        "text": {"type": "plain_text", "text": "Skip today", "emoji": True},
                        "style": "danger",
                        "value": "skip_standup",
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Skip standup?"},
                            "text": {
                                "type": "plain_text",
                                "text": "Skip today's standup? Your teammates won't see an update from you.",
                            },
                            "confirm": {"type": "plain_text", "text": "Yes, skip"},
                            "deny": {"type": "plain_text", "text": "Never mind"},
                        },
                    },
                    {
                        "type": "button",
                        "action_id": "im_away",
                        "text": {"type": "plain_text", "text": "I'm away", "emoji": True},
                        "value": "im_away",
                    },
                ],
            },
            {
                "type": "context",
                "block_id": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Or just type your answer below",
                    }
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# Modal: Fill-in standup form (all questions at once)
# ---------------------------------------------------------------------------


def standup_form_modal(questions: list[str], standup_name: str, previous_answers: list[str] | None = None) -> dict:
    """Modal opened when user clicks 'Fill in form'.

    If *previous_answers* is provided, the corresponding fields are
    pre-filled so the user can quickly update rather than retype.
    """
    previous_answers = previous_answers or []
    blocks = []
    for i, question in enumerate(questions):
        prev = previous_answers[i] if i < len(previous_answers) else ""
        element: dict = {
            "type": "rich_text_input",
            "action_id": f"answer_{i}",
        }
        if prev:
            element["initial_value"] = mrkdwn_to_rich_text(prev)
        blocks.append(
            {
                "type": "input",
                "block_id": f"question_{i}",
                "label": {"type": "plain_text", "text": question},
                "element": element,
                "optional": False,
            }
        )

    return {
        "type": "modal",
        "callback_id": "standup_form_modal",
        "title": {"type": "plain_text", "text": standup_name[:24]},
        "submit": {"type": "plain_text", "text": "Submit standup"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Channel message: Standup summary
# ---------------------------------------------------------------------------


def standup_summary_message(
    standup_name: str,
    date: str,
    responses: list[dict],
    group_by: str = "member",
    jira_base_url: str = "",
    zendesk_base_url: str = "",
) -> dict:
    """
    Rich summary posted to channel.

    Each response dict: {name, avatar_url, answers: list[str], questions: list[str], has_blockers}
    """
    total = len(responses)
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🌅 {standup_name} — {date}",
                "emoji": True,
            },
        },
        {"type": "divider"},
    ]

    if not responses:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No responses yet._"},
            }
        )
    else:
        for resp in responses:
            name = resp.get("name", "Unknown")
            has_blockers = resp.get("has_blockers", False)
            answers = resp.get("answers", [])
            questions = resp.get("questions", [])
            avatar_url = resp.get("avatar_url")

            blocker_badge = " 🚨 *Has blockers*" if has_blockers else ""

            # Member header
            member_block: dict = {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{name}*{blocker_badge}"},
            }
            if avatar_url:
                member_block["accessory"] = {
                    "type": "image",
                    "image_url": avatar_url,
                    "alt_text": name,
                }
            blocks.append(member_block)

            # Q&A pairs
            qa_lines = []
            for i, answer in enumerate(answers):
                question = questions[i] if i < len(questions) else f"Q{i + 1}"
                linked = linkify_issues(answer, jira_base_url, zendesk_base_url)
                qa_lines.append(f"*{question}*\n{linked}")

            if qa_lines:
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "\n\n".join(qa_lines)},
                    }
                )

            blocks.append({"type": "divider"})

    # Footer
    responded = len([r for r in responses if r.get("answers")])
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{responded} of {total} members responded_",
                }
            ],
        }
    )

    return {"blocks": blocks}


# ---------------------------------------------------------------------------
# App Home tab
# ---------------------------------------------------------------------------


def app_home_view(
    standups: list[dict],
    user_id: str,
    on_vacation: bool = False,
    streak: int = 0,
    workspace_name: str = "",
    user_tz: str = "",
    is_admin: bool = False,
    other_standups: list[dict] | None = None,
) -> dict:
    """App Home tab — rich standup cards matching Standup & Prosper quality."""
    from datetime import datetime

    import pytz as _pytz

    # Compute local time string for the user
    local_time_str = ""
    if user_tz:
        try:
            tz = _pytz.timezone(user_tz)
            now = datetime.now(tz)
            local_time_str = now.strftime("%A, %-d %B at %-I:%M %p")
        except Exception:
            pass

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🌅 My home", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "Hello there, I'm *Morgenruf*, and this is my home.\n"
                    "If you want to message me, click the *Messages* tab 👆"
                ),
            },
        },
    ]

    # Top action bar — I'm away, Configure (admin only), Get support, Help
    configure_btn = {
        "type": "button",
        "action_id": "open_configure_mode",
        "text": {"type": "plain_text", "text": "⚙️ Configure standups", "emoji": True},
        "value": "configure",
    }
    if on_vacation:
        top_actions = [
            {
                "type": "button",
                "action_id": "vacation_return",
                "text": {"type": "plain_text", "text": "🏖️ I'm back", "emoji": True},
                "style": "primary",
            },
            *([] if not is_admin else [configure_btn]),
            {
                "type": "button",
                "action_id": "open_dashboard",
                "text": {"type": "plain_text", "text": "📊 Get support", "emoji": True},
                "url": "https://api.morgenruf.dev/dashboard",
            },
            {
                "type": "button",
                "action_id": "app_home_help",
                "text": {"type": "plain_text", "text": "📖 Help!", "emoji": True},
                "value": "help",
            },
        ]
    else:
        top_actions = [
            {
                "type": "button",
                "action_id": "im_away",
                "text": {"type": "plain_text", "text": "🏖️ I'm away", "emoji": True},
                "value": "away_today",
            },
            *([] if not is_admin else [configure_btn]),
            {
                "type": "button",
                "action_id": "open_dashboard",
                "text": {"type": "plain_text", "text": "📊 Get support", "emoji": True},
                "url": "https://api.morgenruf.dev/dashboard",
            },
            {
                "type": "button",
                "action_id": "app_home_help",
                "text": {"type": "plain_text", "text": "📖 Help!", "emoji": True},
                "value": "help",
            },
        ]
    blocks.append({"type": "actions", "block_id": "home_actions", "elements": top_actions})

    # Timezone context
    if local_time_str:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"According to Slack and your configured timezone, for you currently it is: *{local_time_str}*.\nIf this is not correct, please correct your Slack timezone setting.",
                    }
                ],
            }
        )

    # Vacation banner
    if on_vacation:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "I hope you'll be awesome when you get back. I won't bother you again until "
                        "then. If you are already back, just send me a message or click *I'm back*. 🏖️"
                    ),
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "I'm back ▶️", "emoji": True},
                    "action_id": "vacation_return",
                    "style": "primary",
                },
            }
        )

    blocks.append({"type": "divider"})

    # Standups section
    if not standups:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*No standups yet.*\n"
                        "Create your first standup to get started, or ask your team admin to add you."
                    ),
                },
                "accessory": {
                    "type": "button",
                    "action_id": "open_create_standup",
                    "text": {"type": "plain_text", "text": "➕ Create a standup", "emoji": True},
                    "style": "primary",
                    "value": "create",
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Your standups:*"},
            }
        )

        for standup in standups:
            standup_id = standup.get("standup_id") or standup.get("id", "")
            name = standup.get("standup_name") or standup.get("name") or "Team Standup"
            channel = standup.get("channel_id", "")
            report_time = standup.get("report_time") or standup.get("schedule_time", "09:00")
            active = standup.get("active", True)
            responded_today = standup.get("user_responded_today", False)
            response_time = standup.get("user_last_response_time")

            # Status indicator
            if not active:
                status_icon = "⏸️"
                status_text = "Paused"
            elif responded_today:
                status_icon = "✅"
                status_text = "Completed"
            else:
                status_icon = "⏳"
                status_text = "Pending"

            # Header line: channel - workspace | name | status
            header = f"<#{channel}>"
            if workspace_name:
                header += f" - *{workspace_name}*"
            header += f" | {name} | {status_icon}"

            # Detail lines
            detail_lines = [header, f"*{status_text}*"]
            if responded_today and response_time:
                detail_lines.append(f"Reported at {response_time} today.")
            elif active:
                detail_lines.append(f"Reports at {report_time} today.")

            # Streak
            if streak > 0:
                streak_emoji = "🔥" if streak >= 5 else "✨"
                detail_lines.append(f"Current standup streak: {streak} {streak_emoji}")

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(detail_lines)},
                    "accessory": {
                        "type": "button",
                        "action_id": "view_previous_standups",
                        "text": {"type": "plain_text", "text": "Previous standups 📅", "emoji": True},
                        "value": str(standup_id),
                    },
                }
            )

            # Action buttons — context-aware
            actions = []
            if active and responded_today:
                actions.append(
                    {
                        "type": "button",
                        "action_id": "start_standup_now",
                        "text": {"type": "plain_text", "text": "🔄 Edit standup", "emoji": True},
                        "value": str(standup_id),
                    }
                )
            elif active:
                actions.append(
                    {
                        "type": "button",
                        "action_id": "start_standup_now",
                        "text": {"type": "plain_text", "text": "📝 Start standup", "emoji": True},
                        "style": "primary",
                        "value": str(standup_id),
                    }
                )

            if is_admin:
                actions.append(
                    {
                        "type": "button",
                        "action_id": "edit_standup",
                        "text": {"type": "plain_text", "text": "Configure"},
                        "value": str(standup_id),
                    }
                )
                if active:
                    actions.append(
                        {
                            "type": "button",
                            "action_id": "standup_overflow",
                            "text": {"type": "plain_text", "text": "Pause"},
                            "value": f"pause_{standup_id}",
                        }
                    )
                else:
                    actions.append(
                        {
                            "type": "button",
                            "action_id": "standup_overflow",
                            "text": {"type": "plain_text", "text": "Enable"},
                            "style": "primary",
                            "value": f"enable_{standup_id}",
                        }
                    )

            if actions:
                blocks.append({"type": "actions", "elements": actions})
            blocks.append({"type": "divider"})

    # Admin: other standups section
    if is_admin and other_standups:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*🔧 Other standups (admin):*"},
            }
        )
        for standup in other_standups:
            standup_id = standup.get("standup_id") or standup.get("id", "")
            name = standup.get("standup_name") or standup.get("name") or "Team Standup"
            channel = standup.get("channel_id", "")
            active = standup.get("active", True)
            members = standup.get("members") or []
            member_count = len(members) if isinstance(members, list) else 0

            status_icon = "⏸️" if not active else "▫️"
            line = f"{status_icon} <#{channel}> | {name} · {member_count} participant{'s' if member_count != 1 else ''}"
            admin_actions = [
                {
                    "type": "button",
                    "action_id": "edit_standup",
                    "text": {"type": "plain_text", "text": "Configure"},
                    "value": str(standup_id),
                },
            ]
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": line}})
            blocks.append({"type": "actions", "elements": admin_actions})

        blocks.append({"type": "divider"})

    # Footer
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "💡 Send me `standup` in a DM to start manually · `skip` to skip today · `I'm away` to go on vacation",
                }
            ],
        }
    )

    return {"type": "home", "blocks": blocks}


# ---------------------------------------------------------------------------
# App Home: Configure mode
# ---------------------------------------------------------------------------


def app_home_configure_view(
    standups: list[dict],
    user_id: str,
    workspace_name: str = "",
) -> dict:
    """App Home tab — Standup Configuration mode matching competitor."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "⚙️ Standup Configuration", "emoji": True},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "close_configure_mode",
                    "text": {"type": "plain_text", "text": "x Close Configuration"},
                    "value": "close",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Standups you can configure:*\nOr create a new standup 👉"},
            "accessory": {
                "type": "button",
                "action_id": "open_create_standup",
                "text": {"type": "plain_text", "text": "📬 Create a standup", "emoji": True},
                "style": "primary",
                "value": "create",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "Don't see the standup you are looking for? That means you "
                    "probably are not a part of it. You can easily join an existing "
                    "standup and edit it in the <https://api.morgenruf.dev/dashboard|Standup Portal>. 👉"
                ),
            },
            "accessory": {
                "type": "button",
                "action_id": "open_dashboard",
                "text": {"type": "plain_text", "text": "Go to Standup Portal 🔗", "emoji": True},
                "url": "https://api.morgenruf.dev/dashboard",
            },
        },
        {"type": "divider"},
    ]

    if not standups:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "No standups configured yet. Create your first one above!"},
            }
        )
    else:
        for standup in standups:
            standup_id = standup.get("standup_id") or standup.get("id", "")
            name = standup.get("standup_name") or standup.get("name") or "Team Standup"
            channel = standup.get("channel_id", "")
            report_time = standup.get("report_time") or standup.get("schedule_time", "09:00")
            tz = standup.get("timezone") or standup.get("schedule_tz", "UTC")
            members = standup.get("members") or standup.get("participants") or []
            days = standup.get("days") or []
            if isinstance(days, str):
                days = [d.strip() for d in days.split(",") if d.strip()]
            member_count = len(members) if isinstance(members, list) else 0
            active = standup.get("active", True)
            questions = standup.get("questions") or []
            q_count = len(questions) if isinstance(questions, list) else 0

            days_label = (
                "Weekdays"
                if set(days) == {"mon", "tue", "wed", "thu", "fri"}
                else ", ".join(d.capitalize() for d in days)
            )

            ws = f" - *{workspace_name}*" if workspace_name else ""
            detail_lines = [
                f"<#{channel}>{ws} | {name} |",
                f"{member_count} participant{'s' if member_count != 1 else ''} · {q_count} question{'s' if q_count != 1 else ''}",
                f"{days_label} @ {report_time} ({tz})",
            ]
            if not active:
                detail_lines.append("*Paused*")

            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(detail_lines)}})

            row = [
                {
                    "type": "button",
                    "action_id": "edit_standup",
                    "text": {"type": "plain_text", "text": "Configure"},
                    "value": str(standup_id),
                },
            ]
            if active:
                row.append(
                    {
                        "type": "button",
                        "action_id": "standup_overflow",
                        "text": {"type": "plain_text", "text": "Pause"},
                        "value": f"pause_{standup_id}",
                    }
                )
            else:
                row.append(
                    {
                        "type": "button",
                        "action_id": "standup_overflow",
                        "text": {"type": "plain_text", "text": "Enable"},
                        "style": "primary",
                        "value": f"enable_{standup_id}",
                    }
                )
            row.append(
                {
                    "type": "button",
                    "action_id": "open_dashboard",
                    "text": {"type": "plain_text", "text": "Details 🔗", "emoji": True},
                    "url": "https://api.morgenruf.dev/dashboard",
                }
            )
            row.append(
                {
                    "type": "button",
                    "action_id": "delete_standup",
                    "text": {"type": "plain_text", "text": "Delete"},
                    "style": "danger",
                    "value": str(standup_id),
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Delete standup?"},
                        "text": {
                            "type": "plain_text",
                            "text": f"Permanently delete '{name}'? This cannot be undone.",
                        },
                        "confirm": {"type": "plain_text", "text": "Yes, delete"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                }
            )
            blocks.append({"type": "actions", "elements": row})
            blocks.append({"type": "divider"})

    return {"type": "home", "blocks": blocks}


# ---------------------------------------------------------------------------
# Modal: Help
# ---------------------------------------------------------------------------


def help_modal() -> dict:
    """Help modal shown from App Home."""
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Morgenruf Help"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🌅 Getting Started", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Morgenruf* runs async standups in Slack. "
                        "At your scheduled time, each member gets a DM with your standup questions. "
                        "Answers are collected and posted as a threaded summary in your standup channel."
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💬 DM Commands", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "• `standup` — Start a standup manually\n"
                        "• `skip` — Skip today's standup\n"
                        "• `I'm away` — Go on vacation (stops DMs)\n"
                        "• `I'm back` — Return from vacation\n"
                        "• `timezone America/New_York` — Set your personal timezone\n"
                        "• `edit` — Edit your last standup (within 30 min)"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "⚙️ Configuration", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "• Click *Configure standups* in App Home to manage standups\n"
                        "• Use the *Configure* button on any standup card to edit settings\n"
                        "• Visit the <https://api.morgenruf.dev/dashboard|Web Dashboard> for advanced analytics and management"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 Features", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "• *Streaks* — Track consecutive standup days\n"
                        "• *Mood tracking* — Team health check after each standup\n"
                        "• *Answer prefill* — Yesterday's answers auto-fill today's form\n"
                        "• *Channel sync* — Auto-add channel members to standups\n"
                        "• *Webhooks* — Push standup data to external systems\n"
                        "• *CSV export* — Download standup data from the dashboard"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Need more help? Visit <https://docs.morgenruf.dev|docs.morgenruf.dev> or <https://api.morgenruf.dev/support|contact support>",
                    }
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Modal: Previous standups history
# ---------------------------------------------------------------------------


def previous_standups_modal(standups: list[dict], standup_name: str = "Standup") -> dict:
    """Modal showing recent standup history for the current user."""
    blocks: list[dict] = []

    if not standups:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No previous standups found._"},
            }
        )
    else:
        for s in standups[:10]:  # Show last 10
            date_str = str(s.get("standup_date", ""))
            yesterday = s.get("yesterday", "") or "—"
            today = s.get("today", "") or "—"
            blockers = s.get("blockers", "") or "None"
            mood = s.get("mood", "")
            mood_str = f"  |  🎭 {mood}" if mood else ""

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{date_str}*{mood_str}",
                    },
                }
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (f"*Yesterday:* {yesterday}\n*Today:* {today}\n*Blockers:* {blockers}"),
                    },
                }
            )
            blocks.append({"type": "divider"})

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": f"📅 {standup_name[:20]}"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks,
    }


# ---------------------------------------------------------------------------
# DM: Away confirmation
# ---------------------------------------------------------------------------


def away_confirmation_message(until: str = "tomorrow") -> dict:
    """Simple DM confirming user is marked as away."""
    return {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🏖️ Got it! You're marked as away until *{until}*. We'll skip your standup for today.",
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Issue auto-linking
# ---------------------------------------------------------------------------


def linkify_issues(text: str, jira_base_url: str = "", zendesk_base_url: str = "") -> str:
    """Replace issue patterns and URLs with Slack mrkdwn links, and normalise bullets.

    Zendesk tickets are matched first (``{ZD-NNN}``) so they are not
    consumed by the generic Jira pattern.

    Args:
        text: Raw standup response text.
        jira_base_url: e.g. ``"https://myorg.atlassian.net"``.
        zendesk_base_url: e.g. ``"https://myorg.zendesk.com"``.
    """
    if zendesk_base_url:

        def _zd(m: re.Match) -> str:  # type: ignore[type-arg]
            num = m.group(1)
            return f"<{zendesk_base_url}/agent/tickets/{num}|ZD-{num}>"

        text = re.sub(r"\{ZD-(\d+)\}", _zd, text)

    if jira_base_url:

        def _jira(m: re.Match) -> str:  # type: ignore[type-arg]
            key = m.group(1)
            return f"<{jira_base_url}/browse/{key}|{key}>"

        text = re.sub(r"\{([A-Z][A-Z0-9_]+-\d+)\}", _jira, text)

    # Convert markdown-style links [text](url) → Slack mrkdwn <url|text>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"<\2|\1>", text)

    # Auto-link bare URLs not already inside < > brackets
    text = re.sub(r"(?<![<|])(https?://[^\s>]+)", r"<\1>", text)

    # Normalise bullet points: lines starting with - or * → •
    text = re.sub(r"(?m)^[\-\*]\s+", "• ", text)

    return text


# ---------------------------------------------------------------------------
# Summary builders (by-member and by-question)
# ---------------------------------------------------------------------------


def build_summary_by_member(
    responses: list[dict],
    questions: list[str],
    user_profiles: dict | None = None,
    jira_base_url: str = "",
    zendesk_base_url: str = "",
    edit_window_open: set | None = None,
) -> list[dict]:
    """Build Slack blocks for a standup summary grouped by member.

    Each response dict must contain: ``user_id``, ``yesterday``, ``today``,
    ``blockers``, and optionally ``id``.  ``user_profiles`` maps
    ``user_id`` → ``{"display_name": str, "avatar_url": str}``.
    ``edit_window_open`` is a set of user_ids who may still edit.
    """
    user_profiles = user_profiles or {}
    edit_window_open = edit_window_open or set()

    q_labels = (
        list(questions)
        if questions
        else [
            "What did you complete yesterday?",
            "What are you working on today?",
            "Any blockers?",
        ]
    )
    answer_keys = ["yesterday", "today", "blockers"]

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 Today's Standup Summary", "emoji": True},
        },
        {"type": "divider"},
    ]

    for resp in responses:
        user_id: str = resp["user_id"]
        profile = user_profiles.get(user_id, {})
        display_name: str = profile.get("display_name") or f"<@{user_id}>"
        avatar_url: str = profile.get("avatar_url", "")

        # Context block: avatar + name
        context_elements: list[dict] = []
        if avatar_url:
            context_elements.append(
                {
                    "type": "image",
                    "image_url": avatar_url,
                    "alt_text": display_name,
                }
            )
        context_elements.append({"type": "mrkdwn", "text": f"*{display_name}*"})
        blocks.append({"type": "context", "elements": context_elements})

        # Q&A section
        qa_lines: list[str] = []
        for idx, key in enumerate(answer_keys):
            raw = resp.get(key, "") or ""
            linked = linkify_issues(raw, jira_base_url, zendesk_base_url)
            label = q_labels[idx] if idx < len(q_labels) else key.capitalize()
            qa_lines.append(f"*{label}*\n{linked}")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n\n".join(qa_lines)},
            }
        )

        # Edit button (only if within window)
        if user_id in edit_window_open:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✏️ Edit my standup", "emoji": True},
                            "action_id": "standup_edit",
                            "value": str(resp.get("id", "")),
                            "style": "primary",
                        }
                    ],
                }
            )

        blocks.append({"type": "divider"})

    return blocks


def build_summary_by_question(
    responses: list[dict],
    questions: list[str],
    user_profiles: dict | None = None,
    jira_base_url: str = "",
    zendesk_base_url: str = "",
) -> list[dict]:
    """Build Slack blocks for a standup summary grouped by question.

    Shows all answers to Q1 first, then Q2, etc.

    Each response dict must contain: ``user_id``, ``yesterday``, ``today``,
    ``blockers``.  ``user_profiles`` maps
    ``user_id`` → ``{"display_name": str, "avatar_url": str}``.
    """
    user_profiles = user_profiles or {}

    q_labels = (
        list(questions)
        if questions
        else [
            "What did you complete yesterday?",
            "What are you working on today?",
            "Any blockers?",
        ]
    )
    answer_keys = ["yesterday", "today", "blockers"]

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 Today's Standup Summary", "emoji": True},
        },
        {"type": "divider"},
    ]

    for idx, key in enumerate(answer_keys):
        label = q_labels[idx] if idx < len(q_labels) else key.capitalize()
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{label}*"},
            }
        )

        for resp in responses:
            user_id: str = resp["user_id"]
            profile = user_profiles.get(user_id, {})
            display_name: str = profile.get("display_name") or f"<@{user_id}>"
            avatar_url: str = profile.get("avatar_url", "")

            raw = resp.get(key, "") or ""
            linked = linkify_issues(raw, jira_base_url, zendesk_base_url)

            context_elements: list[dict] = []
            if avatar_url:
                context_elements.append(
                    {
                        "type": "image",
                        "image_url": avatar_url,
                        "alt_text": display_name,
                    }
                )
            context_elements.append(
                {
                    "type": "mrkdwn",
                    "text": f"*{display_name}*: {linked}",
                }
            )
            blocks.append({"type": "context", "elements": context_elements})

        blocks.append({"type": "divider"})

    return blocks
