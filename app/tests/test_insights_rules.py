"""Detecting a blocker that keeps coming back.

A blocker mentioned once is work. The same blocker on three days running is
someone stuck, and nobody noticing is the failure this is meant to catch.
"""

from __future__ import annotations

from datetime import date

from src.modules.insights.rules import find_blocker_runs, normalise, similar


def d(day):
    return date(2026, 9, day)


# ── normalise ────────────────────────────────────────────────────────────────

def test_normalise_lowercases_and_strips_punctuation():
    # "on" is filler and is dropped too, which is what lets a restatement match
    assert normalise("Waiting on Infra!") == "waiting infra"


def test_normalise_collapses_whitespace():
    assert normalise("  waiting   on\n infra ") == "waiting infra"


def test_normalise_drops_filler_so_restatements_match():
    assert normalise("still waiting on the infra team") == normalise("waiting on infra team")


def test_normalise_handles_empty():
    assert normalise("") == ""
    assert normalise(None) == ""


# ── similar ──────────────────────────────────────────────────────────────────

def test_identical_text_is_similar():
    assert similar("waiting on infra", "waiting on infra") is True


def test_a_restatement_is_similar():
    assert similar("waiting on the infra team", "still waiting on infra team") is True


def test_unrelated_blockers_are_not_similar():
    assert similar("waiting on infra", "need design review for the modal") is False


def test_a_short_blocker_does_not_match_everything():
    """Two one-word blockers should not collapse into each other."""
    assert similar("blocked", "waiting") is False


def test_empty_text_is_never_similar():
    assert similar("", "waiting on infra") is False
    assert similar("", "") is False


# ── find_blocker_runs ────────────────────────────────────────────────────────

def rows(*pairs):
    return [{"standup_date": dt, "blockers": txt} for dt, txt in pairs]


def test_a_single_blocker_is_not_a_run():
    assert find_blocker_runs(rows((d(14), "waiting on infra")), min_days=3) == []


def test_three_consecutive_days_of_the_same_blocker_is_a_run():
    r = find_blocker_runs(
        rows((d(14), "waiting on infra"),
             (d(15), "still waiting on infra"),
             (d(16), "waiting on the infra team")),
        min_days=3,
    )
    assert len(r) == 1
    assert r[0]["days"] == 3
    assert r[0]["first_seen"] == d(14)
    assert r[0]["last_seen"] == d(16)


def test_a_different_blocker_breaks_the_run():
    r = find_blocker_runs(
        rows((d(14), "waiting on infra"),
             (d(15), "need a design review"),
             (d(16), "waiting on infra")),
        min_days=3,
    )
    assert r == []


def test_a_weekend_does_not_break_a_run():
    """2026-09-18 is a Friday and 09-21 the Monday. Standups skip weekends, so
    Friday into Monday is consecutive for this purpose."""
    r = find_blocker_runs(
        rows((d(17), "waiting on infra"),
             (d(18), "waiting on infra"),
             (d(21), "waiting on infra")),
        min_days=3,
    )
    assert len(r) == 1
    assert r[0]["days"] == 3


def test_a_missed_weekday_breaks_the_run():
    """Skipping a Tuesday means they were not blocked on it, or not there.

    With min_days=3 nothing qualifies, because the gap splits three days into
    a one and a two. At min_days=2 the surviving stretch starts after the gap.
    """
    args = rows((d(14), "waiting on infra"),
                (d(16), "waiting on infra"),
                (d(17), "waiting on infra"))
    assert find_blocker_runs(args, min_days=3) == []
    after = find_blocker_runs(args, min_days=2)
    assert len(after) == 1
    assert after[0]["first_seen"] == d(16)


def test_the_longest_run_is_reported_not_every_window():
    r = find_blocker_runs(
        rows((d(14), "waiting on infra"),
             (d(15), "waiting on infra"),
             (d(16), "waiting on infra"),
             (d(17), "waiting on infra")),
        min_days=3,
    )
    assert len(r) == 1
    assert r[0]["days"] == 4


def test_two_separate_runs_are_both_reported():
    r = find_blocker_runs(
        rows((d(1), "waiting on infra"), (d(2), "waiting on infra"), (d(3), "waiting on infra"),
             (d(10), "design review"), (d(11), "design review"), (d(14), "design review")),
        min_days=3,
    )
    assert len(r) == 2
    assert {x["days"] for x in r} == {3}


def test_rows_out_of_order_are_handled():
    r = find_blocker_runs(
        rows((d(16), "waiting on infra"),
             (d(14), "waiting on infra"),
             (d(15), "waiting on infra")),
        min_days=3,
    )
    assert len(r) == 1 and r[0]["first_seen"] == d(14)


def test_blank_and_none_blockers_are_ignored():
    """'none' is what the bot tells people to type when they are clear."""
    r = find_blocker_runs(
        rows((d(14), "none"), (d(15), ""), (d(16), None), (d(17), "none")),
        min_days=2,
    )
    assert r == []


def test_the_reported_text_is_the_most_recent_wording():
    r = find_blocker_runs(
        rows((d(14), "waiting on infra"),
             (d(15), "still waiting on infra"),
             (d(16), "waiting on infra for the third day")),
        min_days=3,
    )
    assert r[0]["text"] == "waiting on infra for the third day"
