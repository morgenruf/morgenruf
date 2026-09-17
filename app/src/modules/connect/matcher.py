"""Who meets whom this round.

A pure function with no I/O, so the part with real logic is fully testable
without a database or a Slack client.

The cost of putting two people together is how often they have already met,
plus a penalty if that was recent. Never-paired costs nothing, so "no repeats
until the pool is exhausted" falls out of the cost function rather than needing
a rule of its own.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PairStat:
    times_paired: int
    last_round_id: int | None = None


# How much a recent meeting adds on top of the raw count. Large enough that a
# fresh partner always wins while one exists.
_RECENCY_PENALTY = 100


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _cost(a: str, b: str, history: dict, current_round: int | None) -> int:
    stat = history.get(_key(a, b))
    if stat is None:
        return 0
    cost = stat.times_paired
    if current_round is not None and stat.last_round_id is not None:
        if current_round - stat.last_round_id <= 2:
            cost += _RECENCY_PENALTY
    return cost


def _total_cost(member: str, others: list[str], history: dict, current_round: int | None) -> int:
    """How much history this member carries against everyone still unmatched."""
    return sum(_cost(member, o, history, current_round) for o in others if o != member)


def _can_meet(a: str, b: str, timezones: dict[str, str], minimum_hours: float) -> bool:
    from src.modules.connect.hours import can_meet  # noqa: PLC0415

    return can_meet(timezones.get(a, ""), timezones.get(b, ""), minimum_hours)


def match(
    pool: list[str],
    history: dict[tuple[str, str], PairStat],
    seed: int,
    current_round: int | None = None,
    timezones: dict[str, str] | None = None,
    minimum_overlap_hours: float = 0.0,
) -> list[list[str]]:
    """Group a pool into pairs, with one trio when the count is odd.

    `seed` derives from the round id rather than the clock, so a retried round
    produces the same matching and a test can assert on it.

    Returns an empty list for a pool of fewer than two: nobody is ever told
    they have been matched with no one.

    With `minimum_overlap_hours` above zero, a pair must share that much of a
    working day, judged from `timezones`. Someone left with no reachable
    partner is not matched at all this round rather than handed an
    introduction they cannot act on.
    """
    if len(pool) < 2:
        return []

    rng = random.Random(seed)
    # Sort first so the caller's ordering cannot change the result, then
    # shuffle deterministically from the seed.
    remaining = sorted(pool)
    rng.shuffle(remaining)

    groups: list[list[str]] = []
    # People the working-hours constraint could not place. They are not matched
    # this round rather than handed an introduction they cannot act on.
    unmatched: list[str] = []
    while len(remaining) >= 2:
        # Most constrained first. The person carrying the most history has the
        # fewest good options, so letting them choose first avoids stranding
        # them with their worst partner. Picking the globally cheapest pair
        # instead would hand the cheap pairs to people who had plenty of
        # choices and leave the constrained one with what was left.
        a = max(remaining, key=lambda m: (_total_cost(m, remaining, history, current_round), -remaining.index(m)))
        remaining.remove(a)
        candidates = remaining
        if minimum_overlap_hours > 0:
            candidates = [m for m in remaining if _can_meet(a, m, timezones or {}, minimum_overlap_hours)]
            if not candidates:
                # Nobody shares enough of a day with them. Leaving them out is
                # honest; pairing them anyway produces a chat that cannot happen.
                unmatched.append(a)
                continue
        best = min(candidates, key=lambda b: (_cost(a, b, history, current_round), remaining.index(b)))
        remaining.remove(best)
        groups.append(sorted([a, best]))

    if remaining and groups:
        leftover = remaining.pop()
        if minimum_overlap_hours > 0:
            reachable_groups = [
                g for g in groups if all(_can_meet(leftover, m, timezones or {}, minimum_overlap_hours) for m in g)
            ]
            if not reachable_groups:
                return groups
            groups_for_leftover = reachable_groups
        else:
            groups_for_leftover = groups
        # The odd person joins whichever pair they know least, rather than an
        # arbitrary one.
        target = min(
            groups_for_leftover,
            key=lambda g: _cost(leftover, g[0], history, current_round) + _cost(leftover, g[1], history, current_round),
        )
        target.append(leftover)
        target.sort()

    return groups
