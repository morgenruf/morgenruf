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


def intro_message(member_ids: list[str], seed: int, program_id: int) -> tuple[str, list]:
    mentions = _mentions(member_ids)
    group = "Three of you this round, so nobody sits out." if len(member_ids) > 2 else "Just the two of you."
    text = f"Coffee chat: {mentions}, you have been matched."

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "☕ Coffee chat", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"{mentions}, you have been matched. Say hello right here."}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": f"{group} Fifteen minutes is plenty, and any time this week works."}]},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*Something to open with*\n> {icebreaker(seed)}"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Skip this round"},
             "action_id": "connect:skip_round", "value": str(program_id)},
            {"type": "button", "text": {"type": "plain_text", "text": "Pause coffee chats"},
             "action_id": "connect:pause", "value": str(program_id)},
        ]},
    ]
    return text, blocks


def nudge_message(seed: int) -> tuple[str, list]:
    text = "Still time to say hello."
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
         "text": "*Still time to say hello.*\nThis chat is still open, and one message is enough to start it."}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*Another one to try*\n> {icebreaker(seed + 3)}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": "You have a few more days before this round closes."}]},
    ]
    return text, blocks


def did_you_meet_message(match_id: int) -> tuple[str, list]:
    text = "Did you get a chance to meet?"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Did you get a chance to meet?*"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "We met"},
             "style": "primary", "action_id": "connect:met_yes", "value": str(match_id)},
            {"type": "button", "text": {"type": "plain_text", "text": "Not yet"},
             "action_id": "connect:met_no", "value": str(match_id)},
        ]},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": "One tap. This answer is the only thing we count."}]},
    ]
    return text, blocks


def random_seed_for(round_id: int, match_id: int) -> int:
    """Stable per match, so a retry shows the same prompt."""
    return (round_id * 31 + match_id) % (2**31)


__all__ = ["intro_message", "nudge_message", "did_you_meet_message", "icebreaker",
           "random_seed_for", "ICEBREAKERS", "random"]
