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
    group_size: int = 2,
    strict_group_size: bool = False,
) -> list[list[str]]:
    """Group a pool into groups of `group_size`, with a larger last one when
    the count does not divide evenly.

    `group_size` of 2 is the original behaviour exactly: pairs, with one trio
    when the count is odd. A larger size builds each group around the most
    constrained person still waiting and adds whoever they know least, which
    is the same rule as the pair case applied repeatedly.

    `strict_group_size` leaves the remainder unmatched rather than growing a
    group past the requested size. Useful when the size is the point, as in a
    lunch for exactly four.

    `seed` derives from the round id rather than the clock, so a retried round
    produces the same matching and a test can assert on it.

    Returns an empty list for a pool of fewer than two: nobody is ever told
    they have been matched with no one.

    With `minimum_overlap_hours` above zero, a pair must share that much of a
    working day, judged from `timezones`. Someone left with no reachable
    partner is not matched at all this round rather than handed an
    introduction they cannot act on.
    """
    size = max(2, int(group_size or 2))
    if len(pool) < size and (strict_group_size or len(pool) < 2):
        # Strict means a group of the wrong size is worse than none. Otherwise
        # a pool too small for the requested size still gets one smaller group,
        # because two people meeting beats nobody meeting.
        return []
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
    while len(remaining) >= size:
        # Most constrained first. The person carrying the most history has the
        # fewest good options, so letting them choose first avoids stranding
        # them with their worst partner. Picking the globally cheapest pair
        # instead would hand the cheap pairs to people who had plenty of
        # choices and leave the constrained one with what was left.
        a = max(remaining, key=lambda m: (_total_cost(m, remaining, history, current_round), -remaining.index(m)))
        remaining.remove(a)
        group = [a]

        # Then fill the group one at a time, each time taking whoever the
        # group as a whole knows least. Same rule as the pair case, applied
        # until the group is full.
        stranded = False
        while len(group) < size:
            candidates = remaining
            if minimum_overlap_hours > 0:
                candidates = [
                    m for m in remaining if all(_can_meet(m, g, timezones or {}, minimum_overlap_hours) for g in group)
                ]
            if not candidates:
                # Nobody shares enough of a day with them. Leaving them out is
                # honest; pairing them anyway produces a chat that cannot happen.
                stranded = True
                break
            nxt = min(
                candidates,
                key=lambda b: (sum(_cost(b, g, history, current_round) for g in group), remaining.index(b)),
            )
            remaining.remove(nxt)
            group.append(nxt)

        if stranded:
            if len(group) >= 2 and not strict_group_size:
                # A smaller group that can actually meet beats no group.
                groups.append(sorted(group))
            else:
                unmatched.extend(group[:1])
                remaining.extend(group[1:])
                remaining.sort()
            continue
        groups.append(sorted(group))

    # The remainder. Strict mode leaves them out rather than growing a group
    # past the size that was asked for.
    #
    # Two or more left over form their own group instead of being distributed:
    # ten people in groups of four is 4, 4 and 2, not two groups of five. Only
    # a single leftover joins an existing group, which is the odd-one-out case
    # the pair matching has always handled.
    if not strict_group_size and len(remaining) >= 2:
        leftovers = sorted(remaining)
        if minimum_overlap_hours > 0:
            reachable = [
                m
                for m in leftovers
                if any(_can_meet(m, o, timezones or {}, minimum_overlap_hours) for o in leftovers if o != m)
            ]
            leftovers = reachable
        if len(leftovers) >= 2:
            for m in leftovers:
                remaining.remove(m)
            groups.append(sorted(leftovers))

    while remaining and groups and not strict_group_size:
        leftover = remaining.pop()
        if minimum_overlap_hours > 0:
            reachable_groups = [
                g for g in groups if all(_can_meet(leftover, m, timezones or {}, minimum_overlap_hours) for m in g)
            ]
            if not reachable_groups:
                # This person cannot join any existing group; the others in the
                # remainder might still be able to, so keep going.
                continue
            groups_for_leftover = reachable_groups
        else:
            groups_for_leftover = groups
        # The odd person joins whichever pair they know least, rather than an
        # arbitrary one.
        target = min(
            groups_for_leftover,
            key=lambda g: (sum(_cost(leftover, m, history, current_round) for m in g), len(g)),
        )
        target.append(leftover)
        target.sort()

    return groups
