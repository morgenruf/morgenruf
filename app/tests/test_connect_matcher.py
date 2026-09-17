"""Pairing algorithm: pairs, a trio for odd counts, no repeats until exhausted."""

from __future__ import annotations

from src.modules.connect.matcher import PairStat, match


def key(a, b):
    return (a, b) if a < b else (b, a)


def flat(groups):
    return sorted(m for g in groups for m in g)


def test_everyone_is_matched_exactly_once():
    pool = ["U1", "U2", "U3", "U4"]
    groups = match(pool, {}, seed=1)
    assert flat(groups) == pool


def test_an_even_pool_makes_only_pairs():
    groups = match(["U1", "U2", "U3", "U4"], {}, seed=1)
    assert sorted(len(g) for g in groups) == [2, 2]


def test_an_odd_pool_makes_one_trio_and_nobody_sits_out():
    pool = ["U1", "U2", "U3", "U4", "U5"]
    groups = match(pool, {}, seed=1)
    assert sorted(len(g) for g in groups) == [2, 3]
    assert flat(groups) == pool


def test_a_pool_of_three_is_a_single_trio():
    groups = match(["U1", "U2", "U3"], {}, seed=1)
    assert len(groups) == 1
    assert sorted(groups[0]) == ["U1", "U2", "U3"]


def test_a_pool_of_two_is_one_pair():
    assert match(["U1", "U2"], {}, seed=1) == [["U1", "U2"]]


def test_a_pool_of_one_produces_nothing():
    """One person must never be told they have been matched with nobody."""
    assert match(["U1"], {}, seed=1) == []


def test_an_empty_pool_produces_nothing():
    assert match([], {}, seed=1) == []


def test_previously_paired_people_are_avoided_while_fresh_partners_remain():
    pool = ["U1", "U2", "U3", "U4"]
    history = {key("U1", "U2"): PairStat(times_paired=3, last_round_id=9)}
    groups = match(pool, history, seed=1)
    pairs = {tuple(sorted(g)) for g in groups}
    assert ("U1", "U2") not in pairs


def test_a_repeat_is_allowed_once_the_pool_is_exhausted():
    """With only two people, the same pair must recur rather than nobody meeting."""
    history = {key("U1", "U2"): PairStat(times_paired=5, last_round_id=1)}
    assert match(["U1", "U2"], history, seed=1) == [["U1", "U2"]]


def test_the_least_paired_partner_is_preferred():
    pool = ["U1", "U2", "U3", "U4"]
    history = {
        key("U1", "U2"): PairStat(times_paired=4, last_round_id=1),
        key("U1", "U3"): PairStat(times_paired=1, last_round_id=1),
        key("U1", "U4"): PairStat(times_paired=9, last_round_id=1),
    }
    groups = match(pool, history, seed=1)
    partner = next(set(g) - {"U1"} for g in groups if "U1" in g)
    assert partner == {"U3"}


def test_the_same_seed_gives_the_same_matching():
    pool = ["U1", "U2", "U3", "U4", "U5", "U6"]
    assert match(pool, {}, seed=42) == match(pool, {}, seed=42)


def test_a_different_seed_can_give_a_different_matching():
    """Without this the same people meet every round on an untouched history."""
    pool = [f"U{i}" for i in range(1, 11)]
    results = {tuple(tuple(g) for g in match(pool, {}, seed=s)) for s in range(12)}
    assert len(results) > 1


def test_input_order_does_not_change_the_result_for_a_given_seed():
    pool = ["U1", "U2", "U3", "U4"]
    assert match(pool, {}, seed=7) == match(list(reversed(pool)), {}, seed=7)


def test_the_trio_forms_around_the_pair_the_extra_member_knows_least():
    """Asserts the rule, not one arrangement.

    Which member ends up spare depends on the shuffle, so pinning a specific
    trio would be testing the seed. What must hold is that the spare member
    joined the pair they had the least history with.
    """
    pool = ["U1", "U2", "U3", "U4", "U5"]
    history = {
        key("U1", "U2"): PairStat(times_paired=6, last_round_id=1),
        key("U1", "U3"): PairStat(times_paired=6, last_round_id=1),
        key("U4", "U5"): PairStat(times_paired=6, last_round_id=1),
    }
    groups = match(pool, history, seed=3, current_round=10)
    trio = next(g for g in groups if len(g) == 3)
    pair = next(g for g in groups if len(g) == 2)

    # Whoever joined the trio is the member whose removal leaves a valid pair.
    from src.modules.connect.matcher import _cost

    def combined(member, two):
        return _cost(member, two[0], history, 10) + _cost(member, two[1], history, 10)

    candidates = [(m, [x for x in trio if x != m]) for m in trio]
    joiner, base = min(candidates, key=lambda c: combined(c[0], c[1]))
    assert combined(joiner, base) <= combined(joiner, pair)
