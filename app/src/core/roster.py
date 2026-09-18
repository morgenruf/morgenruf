"""Shared eligibility.

One question, one answer, for every module: who in this workspace can be
contacted right now. Standup filtered this inline, so extracting it means a
second module cannot accidentally disagree about who is away or who has left.

Bots are not filtered here. They never enter the members table in the first
place: the channel sync drops them at write time (see slack_users.is_human).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.core import db


@dataclass(frozen=True)
class Member:
    """One contactable person.

    `name` and `avatar` are here because every surface that lists people needs
    them, and a caller that reaches for a field this class does not have gets
    an empty string from getattr rather than an error: the coffee chat member
    table asked for `real_name` and `avatar`, got neither, and showed raw
    Slack ids with no faces for as long as it had existed.
    """

    user_id: str
    name: str
    tz: str
    avatar: str = ""


def eligible_members(team_id: str, exclude: Iterable[str] = ()) -> list[Member]:
    """Members who are active, not on vacation, and not explicitly excluded.

    `active` and `on_vacation` arrived in later migrations, so a row missing
    either key is treated as the permissive default rather than raising.
    """
    skip = set(exclude)
    out: list[Member] = []
    for row in db.get_all_members(team_id):
        if not row.get("active", True):
            continue
        if row.get("on_vacation", False):
            continue
        if row["user_id"] in skip:
            continue
        out.append(
            Member(
                user_id=row["user_id"],
                name=row.get("real_name") or row.get("display_name") or "",
                tz=row.get("tz") or "UTC",
                avatar=row.get("avatar_url") or "",
            )
        )
    return out
