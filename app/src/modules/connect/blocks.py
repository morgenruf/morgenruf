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


def intro_message(member_ids: list[str], seed: int, program_id: int) -> tuple[str, list]:
    names = ", ".join(f"<@{m}>" for m in member_ids[:-1])
    mentions = f"{names} and <@{member_ids[-1]}>" if len(member_ids) > 1 else f"<@{member_ids[0]}>"
    trio = " You are a three this round, so nobody sits out." if len(member_ids) > 2 else ""
    text = f"Hi {mentions}, you have been matched for a coffee chat."

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*Hi {mentions}, you have been matched for a coffee chat.*{trio}"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"Something to open with:\n> {icebreaker(seed)}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": "Find a time that suits you both. Fifteen minutes is plenty."}]},
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
         "text": f"Still time to say hello. Here is another one to start with:\n> {icebreaker(seed + 3)}"}},
    ]
    return text, blocks


def did_you_meet_message(match_id: int) -> tuple[str, list]:
    text = "Did you two get a chance to meet?"
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Did you get a chance to meet?*"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "We met"},
             "style": "primary", "action_id": "connect:met_yes", "value": str(match_id)},
            {"type": "button", "text": {"type": "plain_text", "text": "Not yet"},
             "action_id": "connect:met_no", "value": str(match_id)},
        ]},
    ]
    return text, blocks


def random_seed_for(round_id: int, match_id: int) -> int:
    """Stable per match, so a retry shows the same prompt."""
    return (round_id * 31 + match_id) % (2**31)


__all__ = ["intro_message", "nudge_message", "did_you_meet_message", "icebreaker",
           "random_seed_for", "ICEBREAKERS", "random"]
