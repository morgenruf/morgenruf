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


def _timezone_options() -> list[dict]:
    zones = [
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
    return [{"text": {"type": "plain_text", "text": label}, "value": value} for value, label in zones]


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


def create_standup_modal(existing_config: dict | None = None) -> dict:
    """
    Full 'Create a standup' modal matching Standup & Prosper UX.
    Pass existing_config to pre-fill fields when editing.
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
    selected_tz = _find_option(tz_options, cfg.get("timezone", "UTC")) or tz_options[0]
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
        {"text": {"type": "plain_text", "text": "Project"}, "value": "project"},
    ]
    selected_group = _find_option(group_by_options, cfg.get("group_by", "member")) or group_by_options[0]

    blocks = [
        # Channel
        {
            "type": "input",
            "block_id": "standup_channel",
            "label": {"type": "plain_text", "text": "Standup channel"},
            "element": {
                "type": "channels_select",
                "action_id": "standup_channel",
                "placeholder": {"type": "plain_text", "text": "Select a channel"},
                **({"initial_channel": cfg["channel_id"]} if cfg.get("channel_id") else {}),
            },
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
                "type": "static_select",
                "action_id": "timezone",
                "options": tz_options,
                "initial_option": selected_tz,
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
    ]

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
            "type": "plain_text_input",
            "action_id": f"answer_{i}",
            "multiline": True,
            "placeholder": {"type": "plain_text", "text": "Type your answer…"},
        }
        if prev:
            element["initial_value"] = prev
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
) -> dict:
    """App Home tab view with rich standup cards, streak, and away toggle."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🌅 Morgenruf", "emoji": True},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Hello! I'm *Morgenruf*, your standup bot{' for ' + workspace_name if workspace_name else ''}.",
            },
        },
    ]

    # Vacation banner
    if on_vacation:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🌴 *You're currently on vacation.* I won't send you standup reminders until you're back.",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "I'm back!", "emoji": True},
                    "action_id": "vacation_return",
                    "style": "primary",
                },
            }
        )

    # Action buttons
    action_elements = [
        {
            "type": "button",
            "action_id": "open_create_standup",
            "text": {"type": "plain_text", "text": "➕ Create a standup", "emoji": True},
            "style": "primary",
            "value": "create",
        },
    ]
    if not on_vacation:
        action_elements.append(
            {
                "type": "button",
                "action_id": "im_away",
                "text": {"type": "plain_text", "text": "🏖️ I'm away", "emoji": True},
                "value": "away_today",
            }
        )
    action_elements.append(
        {
            "type": "button",
            "action_id": "open_dashboard",
            "text": {"type": "plain_text", "text": "🔧 Dashboard", "emoji": True},
            "url": "https://api.morgenruf.dev/dashboard",
        }
    )
    blocks.append({"type": "actions", "block_id": "home_actions", "elements": action_elements})
    blocks.append({"type": "divider"})

    if not standups:
        blocks += [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*No standups yet.*\nCreate your first standup to get started.",
                },
            }
        ]
    else:
        # Streak display
        if streak > 0:
            streak_emoji = "🔥" if streak >= 5 else "✨"
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{streak_emoji} *Current standup streak: {streak}* day{'s' if streak != 1 else ''}",
                    },
                }
            )

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Your standups:*",
                },
            }
        )

        for standup in standups:
            standup_id = standup.get("standup_id") or standup.get("id", "")
            name = standup.get("standup_name") or standup.get("name") or "Team Standup"
            channel = standup.get("channel_id", "")
            report_time = standup.get("report_time") or standup.get("schedule_time", "09:00")
            timezone = standup.get("timezone") or standup.get("schedule_tz", "UTC")
            members = standup.get("members") or standup.get("participants") or []
            days = standup.get("days") or []
            if isinstance(days, str):
                days = [d.strip() for d in days.split(",") if d.strip()]
            days_str = ", ".join(d.capitalize() for d in days) if days else "Weekdays"
            member_count = len(members) if isinstance(members, list) else 0
            active = standup.get("active", True)

            status = "Active" if active else "Paused"
            status_icon = "🟢" if active else "⏸️"

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{status_icon} *{name}*\n"
                            f"<#{channel}> · {report_time} ({timezone})\n"
                            f"{days_str} · {member_count} member{'s' if member_count != 1 else ''} · {status}"
                        ),
                    },
                    "accessory": {
                        "type": "overflow",
                        "action_id": "standup_overflow",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": "✏️ Edit"},
                                "value": f"edit_{standup_id}",
                            },
                            {
                                "text": {"type": "plain_text", "text": "⏸️ Pause" if active else "▶️ Enable"},
                                "value": f"pause_{standup_id}" if active else f"enable_{standup_id}",
                            },
                            {
                                "text": {"type": "plain_text", "text": "🗑️ Delete"},
                                "value": f"delete_{standup_id}",
                            },
                        ],
                    },
                }
            )

            # Quick action buttons per standup
            standup_actions = [
                {
                    "type": "button",
                    "action_id": "start_standup_now",
                    "text": {"type": "plain_text", "text": "📝 Start standup", "emoji": True},
                    "value": str(standup_id),
                },
                {
                    "type": "button",
                    "action_id": "view_previous_standups",
                    "text": {"type": "plain_text", "text": "📅 Previous standups", "emoji": True},
                    "value": str(standup_id),
                },
            ]
            blocks.append({"type": "actions", "elements": standup_actions})
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
    """Replace {PROJ-123} and {ZD-123} patterns with Slack mrkdwn links.

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
