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


def match(
    pool: list[str],
    history: dict[tuple[str, str], PairStat],
    seed: int,
    current_round: int | None = None,
) -> list[list[str]]:
    """Group a pool into pairs, with one trio when the count is odd.

    `seed` derives from the round id rather than the clock, so a retried round
    produces the same matching and a test can assert on it.

    Returns an empty list for a pool of fewer than two: nobody is ever told
    they have been matched with no one.
    """
    if len(pool) < 2:
        return []

    rng = random.Random(seed)
    # Sort first so the caller's ordering cannot change the result, then
    # shuffle deterministically from the seed.
    remaining = sorted(pool)
    rng.shuffle(remaining)

    groups: list[list[str]] = []
    while len(remaining) >= 2:
        # Most constrained first. The person carrying the most history has the
        # fewest good options, so letting them choose first avoids stranding
        # them with their worst partner. Picking the globally cheapest pair
        # instead would hand the cheap pairs to people who had plenty of
        # choices and leave the constrained one with what was left.
        a = max(remaining, key=lambda m: (_total_cost(m, remaining, history, current_round), -remaining.index(m)))
        remaining.remove(a)
        best = min(remaining, key=lambda b: (_cost(a, b, history, current_round), remaining.index(b)))
        remaining.remove(best)
        groups.append(sorted([a, best]))

    if remaining:
        leftover = remaining.pop()
        # The odd person joins whichever pair they know least, rather than an
        # arbitrary one.
        target = min(
            groups,
            key=lambda g: _cost(leftover, g[0], history, current_round) + _cost(leftover, g[1], history, current_round),
        )
        target.append(leftover)
        target.sort()

    return groups
