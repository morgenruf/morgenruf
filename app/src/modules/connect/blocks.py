"""What a matched pair actually receives.

Copy follows Donut's flow: say who you are talking to, give them something to
open with, and make the next action one tap. Opt-out is a button, never a DM
keyword, because standup already claims "skip" as a substring match.
"""

from __future__ import annotations

import random

# Deliberately answerable by a stranger on a Tuesday. Nothing that needs a
# confession, nothing that assumes an office, a family, a country or a budget,
# and nothing that only a senior person can answer without sounding junior.
# Long enough that asking for another one twice still gives something new.
ICEBREAKERS = [
    "What are you working on this week?",
    "What is something you have changed your mind about recently?",
    "What part of the product do you wish you knew better?",
    "What is the best thing you have read or watched lately?",
    "What did you want to be when you were ten?",
    "What is a small thing that made your week better?",
    "Which team do you wish you worked with more often?",
    "What is something you are proud of that nobody noticed?",
    "What is the most useful thing you learned in your first month here?",
    "Which part of your job would surprise someone outside the company?",
    "What is a tool or trick you would recommend to anyone?",
    "What does a good day at work look like for you?",
    "What is something you used to find hard that is now easy?",
    "Which question do you get asked most often, and what is the answer?",
    "What is a decision you are glad someone talked you out of?",
    "What is the smallest change that made the biggest difference to your work?",
    "What do you wish more people asked you about?",
    "What is something you are curious about at the moment?",
    "Which piece of feedback has stuck with you?",
    "What would you spend a free afternoon on?",
    "What is a problem you would happily work on for a year?",
    "Which habit has actually stuck?",
    "What is something you are looking forward to?",
    "What is a thing you have made that you still like?",
]


def icebreaker(seed: int) -> str:
    """Pick a prompt deterministically, so a retried delivery repeats it."""
    return ICEBREAKERS[seed % len(ICEBREAKERS)]


def next_icebreaker(seed: int, exclude: str = "") -> str:
    """A different prompt from the one already on screen.

    Asking for another starter and being handed the same sentence back is
    worse than no button, so the current one is skipped rather than trusted to
    differ by luck.
    """
    if not ICEBREAKERS:
        return ""
    start = seed % len(ICEBREAKERS)
    for step in range(len(ICEBREAKERS)):
        candidate = ICEBREAKERS[(start + step) % len(ICEBREAKERS)]
        if candidate != exclude:
            return candidate
    return ICEBREAKERS[start]


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
    with_icebreaker: bool = True,
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
            # Top right, where Donut's "More options" sits. An overflow rather
            # than a row of buttons: none of these is the thing you came to do,
            # and four equal-weight buttons under an introduction read as a
            # form to fill in.
            "accessory": {
                "type": "overflow",
                "action_id": f"connect:more:{program_id}:{match_id}",
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "\u2728 Another conversation starter"},
                        "value": "starter",
                    },
                    {
                        "text": {"type": "plain_text", "text": "\U0001f30d I need a new match"},
                        "value": "rematch",
                    },
                    {
                        "text": {"type": "plain_text", "text": "\U0001f6ab I am unavailable this round"},
                        "value": "skip",
                    },
                    {
                        "text": {"type": "plain_text", "text": "\u23f8 Pause coffee chats"},
                        "value": "pause",
                    },
                ],
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"{group} {meeting_minutes} minutes is plenty."}],
        },
    ]
    if with_icebreaker:
        blocks.append({"type": "divider"})
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Something to open with*\n> {icebreaker(seed)}"}}
        )

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


ZOOM_LOGO_FILE = "zoom-logo.png"


def zoom_logo_url() -> str:
    """The public url of the official Zoom mark, or "" if it is not installed.

    Zoom's app review guidelines forbid putting their marks on an integration's
    own icon, and proper use of the mark is governed by their Partner Brand
    Guide, so the file is not vendored here. A deployment that has obtained it
    drops it in src/static and it appears; one that has not gets the emoji.

    Checked on disk rather than assumed, because Slack renders a 404 image as a
    broken-image placeholder inside the message, which looks worse than no
    logo at all.
    """
    import os  # noqa: PLC0415

    base = (os.environ.get("APP_URL") or "").rstrip("/")
    if not base:
        return ""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.isfile(os.path.join(here, "static", ZOOM_LOGO_FILE)):
        return ""
    return f"{base}/static/{ZOOM_LOGO_FILE}"


def zoom_offer_blocks(link_url: str) -> list[dict]:
    """The "connect Zoom" prompt, shown only to the person who has not linked.

    Ephemeral for the same reason Donut's is: it is an offer to one reader, and
    putting it in the shared message shows both people an upsell that is
    irrelevant to whichever of them has already linked.

    The heading is its own block because a Slack section carries one accessory,
    and that slot belongs to the button. A context block renders the mark small,
    which is what a logo beside a heading should be.
    """
    logo = zoom_logo_url()
    if logo:
        heading: dict = {
            "type": "context",
            "elements": [
                {"type": "image", "image_url": logo, "alt_text": "Zoom"},
                {"type": "mrkdwn", "text": "*Meet over Zoom*"},
            ],
        }
    else:
        heading = {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "*\U0001f3a5 Meet over Zoom*"}],
        }

    return [
        heading,
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Connect your Zoom account and the meeting gets created for you, "
                "at the time you both agree, on your own account.",
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


def round_stats_message(met: int, answered: int, pairings: int) -> tuple[str, list]:
    """What became of a round, for the channel it belongs to.

    Only the people who answered are counted in the rate, and the denominator
    travels with it. A round where one pair of five answered and met is not
    "20% met", and reporting it that way would make a quiet team look like a
    failing one.
    """
    line = f"{pairings} pair" + ("" if pairings == 1 else "s") + " were introduced."
    if answered:
        line += f" {met} of the {answered} who answered met up."
    else:
        line += " Nobody has said yet whether they met."
    return (
        "Coffee chat round results.",
        [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*How the last round went*\n{line}"}},
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "Answering the check-in is optional, so this counts only replies."}
                ],
            },
        ],
    )
