"""What a matched pair actually receives.

Copy follows Donut's flow: say who you are talking to, give them something to
open with, and make the next action one tap. Opt-out is a button, never a DM
keyword, because standup already claims "skip" as a substring match.
"""

from __future__ import annotations

import random

ICEBREAKERS = [
    "What are you working on this week?",
    "What is something you have changed your mind about recently?",
    "What part of the product do you wish you knew better?",
    "What is the best thing you have read or watched lately?",
    "What did you want to be when you were ten?",
    "What is a small thing that made your week better?",
    "Which team do you wish you worked with more often?",
    "What is something you are proud of that nobody noticed?",
]


def icebreaker(seed: int) -> str:
    """Pick a prompt deterministically, so a retried delivery repeats it."""
    return ICEBREAKERS[seed % len(ICEBREAKERS)]


def _mentions(member_ids: list[str]) -> str:
    """Mentions joined as `A, B and C`, so the message opens by naming people."""
    if len(member_ids) == 1:
        return f"<@{member_ids[0]}>"
    names = ", ".join(f"<@{m}>" for m in member_ids[:-1])
    return f"{names} and <@{member_ids[-1]}>"


def _accepted_line(user_ids: list[str]) -> str:
    """Who has already said a time works, so the second person sees an invitation
    to agree rather than a fresh decision to make."""
    if len(user_ids) == 1:
        return f"_<@{user_ids[0]}> can make this one._"
    return "_" + _mentions(user_ids) + " can all make this one._"


def intro_message(
    member_ids: list[str],
    seed: int,
    program_id: int,
    meeting_link: str = "",
    meeting_minutes: int = 30,
    suggested_times: list | None = None,
    times_are_outside_hours: bool = False,
    match_id: int = 0,
) -> tuple[str, list]:
    """The group DM a match receives.

    suggested_times are hours that fall inside everyone's working day. They are
    proposals, not availability: without calendar access we can say an hour
    suits their timezones, never that they are free, and the message says so
    rather than implying we checked.
    """
    mentions = _mentions(member_ids)
    group = "Three of you this round, so nobody sits out." if len(member_ids) > 2 else "Just the two of you."
    text = f"Coffee chat: {mentions}, you have been matched."

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "☕ Coffee chat", "emoji": True}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{mentions}, you have been matched. Say hello right here.\n"
                    "It is hard to meet people outside your own team when everyone is remote, "
                    "so this introduces two of you every so often."
                ),
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{group} {meeting_minutes} minutes is plenty."}],
        },
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Something to open with*\n> {icebreaker(seed)}"}},
    ]

    if suggested_times:
        # One tap per time that works. The bot settles it the moment everyone
        # has accepted the same slot, which is the part that otherwise does not
        # happen: both people are willing and neither wants to be the one who
        # picks, so the introduction quietly dies in the DM.
        heading = (
            "*Times you could both just about make*"
            if times_are_outside_hours
            else "*Times that suit everyone's hours*"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": heading}})
        for slot in suggested_times[:3]:
            if not isinstance(slot, dict):
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"\u2022 {slot}"}})
                continue
            label = slot.get("label", "")
            utc = slot.get("utc", "")
            accepted = slot.get("accepted") or []
            who = ""
            if accepted:
                who = "\n" + _accepted_line(accepted)
            block = {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{label}*{who}"},
            }
            if utc:
                block["accessory"] = {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Works for me"},
                    "action_id": f"connect:accept_slot:{match_id}:{utc}",
                    "value": utc,
                }
            blocks.append(block)
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Your working days do not overlap, so these sit at the edges of them. "
                            "Nobody has checked your calendars, so pick whichever is actually free."
                            if times_are_outside_hours
                            else "These fit everyone's working hours. Nobody has checked your "
                            "calendars, so pick whichever is actually free."
                        ),
                    }
                ],
            }
        )

    if meeting_link:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Where*\n<{meeting_link}|Join the room>"},
            }
        )

    blocks.extend(
        [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Skip this round"},
                        "action_id": "connect:skip_round",
                        "value": str(program_id),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Pause coffee chats"},
                        "action_id": "connect:pause",
                        "value": str(program_id),
                    },
                ],
            },
        ]
    )
    return text, blocks


def nudge_message(seed: int) -> tuple[str, list]:
    text = "Still time to say hello."
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Still time to say hello.*\nThis chat is still open, and one message is enough to start it.",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Another one to try*\n> {icebreaker(seed + 3)}"}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "You have a few more days before this round closes."}],
        },
    ]
    return text, blocks


def did_you_meet_message(match_id: int) -> tuple[str, list]:
    text = "Did you get a chance to meet?"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Did you get a chance to meet?*"}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "We met"},
                    "style": "primary",
                    "action_id": "connect:met_yes",
                    "value": str(match_id),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Not yet"},
                    "action_id": "connect:met_no",
                    "value": str(match_id),
                },
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "One tap. This answer is the only thing we count."}],
        },
    ]
    return text, blocks


def random_seed_for(round_id: int, match_id: int) -> int:
    """Stable per match, so a retry shows the same prompt."""
    return (round_id * 31 + match_id) % (2**31)


__all__ = [
    "intro_message",
    "nudge_message",
    "did_you_meet_message",
    "icebreaker",
    "random_seed_for",
    "ICEBREAKERS",
    "random",
]


def agreed_message(member_ids: list[str], label: str, add_url: str = "", meeting_link: str = "") -> tuple[str, list]:
    """Everyone has accepted the same time, so say so and stop asking.

    This is the step Donut leaves to the two people. Saying it out loud is what
    turns a willing pair into a meeting: there is a time, both agreed to it, and
    the only thing left is one tap to put it in a calendar.
    """
    mentions = _mentions(member_ids)
    text = f"Settled: {label}."
    lines = [f"*{label}*"]
    if meeting_link:
        lines.append(f"<{meeting_link}|Join the room> when it comes round.")
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"✅ *That is settled then.*\n{mentions} both said this works:"},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
    ]
    if add_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Add to my calendar"},
                        "url": add_url,
                        "action_id": "connect:agreed_add",
                        "style": "primary",
                    }
                ],
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Nobody checked your calendars, so move it between yourselves if something clashes.",
                }
            ],
        }
    )
    return text, blocks


def zoom_offer_blocks(link_url: str) -> list[dict]:
    """The "connect Zoom" prompt, shown only to the person who has not linked.

    Ephemeral for the same reason Donut's is: it is an offer to one reader, and
    putting it in the shared message shows both people an upsell that is
    irrelevant to whichever of them has already linked.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*\U0001f3a5 Meet over Zoom*\nConnect your Zoom account and the meeting gets "
                "created for you, at the time you both agree, on your own account.",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Connect Zoom"},
                "url": link_url,
                "action_id": "connect:zoom_link",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Only you can see this. Nothing is created until a time is agreed.",
                }
            ],
        },
    ]
