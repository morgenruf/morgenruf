"""Turning repeated standup answers into something worth acting on.

A blocker mentioned once is just work. The same blocker three days running is
someone stuck, and the failure this catches is nobody noticing.

Pure functions with no I/O, so the judgement calls here are testable: what
counts as "the same" blocker, and what counts as "consecutive" when standups
only run on weekdays.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# Words that carry no meaning for deciding whether two blockers are the same.
# "Still waiting on infra" and "waiting on infra" are one blocker, not two.
_FILLER = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "still",
    "again",
    "yet",
    "on",
    "in",
    "at",
    "to",
    "for",
    "of",
    "from",
    "and",
    "or",
    "but",
    "with",
    "my",
    "our",
    "i",
    "im",
    "we",
    "it",
    "this",
    "that",
    "some",
    "any",
    "am",
    "s",
    "t",
}

# Answers that mean "nothing is blocking me". The bot tells people to type
# "none", so these are not blockers at all.
_CLEAR = {"none", "no", "nope", "nothing", "n/a", "na", "all good", "clear", "-"}

_SIMILAR_THRESHOLD = 0.5
_MIN_TOKENS_FOR_MATCH = 2


def normalise(text: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace, drop filler words."""
    if not text:
        return ""
    lowered = re.sub(r"[^\w\s]", " ", str(text).lower())
    tokens = [t for t in lowered.split() if t and t not in _FILLER]
    return " ".join(tokens)


def is_clear(text: str | None) -> bool:
    """True when the answer means the person is not blocked."""
    if not text:
        return True
    stripped = re.sub(r"[^\w\s/]", "", str(text).strip().lower())
    return stripped in _CLEAR or normalise(text) == ""


def similar(a: str | None, b: str | None) -> bool:
    """Whether two blocker answers describe the same obstacle.

    Token overlap rather than exact match, because people restate a blocker in
    slightly different words each morning. Blockers of one meaningful word are
    never matched: "blocked" and "waiting" say nothing in common.
    """
    ta, tb = set(normalise(a).split()), set(normalise(b).split())
    if not ta or not tb:
        return False
    if len(ta) < _MIN_TOKENS_FOR_MATCH or len(tb) < _MIN_TOKENS_FOR_MATCH:
        return ta == tb and len(ta) >= _MIN_TOKENS_FOR_MATCH
    overlap = len(ta & tb) / len(ta | tb)
    return overlap >= _SIMILAR_THRESHOLD


def _is_next_working_day(earlier: date, later: date) -> bool:
    """Whether `later` is the next day a standup would have been asked.

    A Friday followed by the Monday is consecutive: standups do not run at the
    weekend, so no answer was expected in between. A skipped weekday is a real
    gap, meaning they were either unblocked or absent.
    """
    step = earlier + timedelta(days=1)
    while step.weekday() >= 5:  # Saturday, Sunday
        step += timedelta(days=1)
    return step == later


def find_blocker_runs(rows: list[dict], min_days: int = 3) -> list[dict]:
    """Stretches where one person reported the same blocker on consecutive days.

    `rows` are that person's standups as {"standup_date", "blockers"}; order
    does not matter. Returns the longest run for each stretch rather than every
    window inside it, and reports the most recent wording, which is the one a
    reader will recognise.
    """
    dated = sorted(
        (r for r in rows if not is_clear(r.get("blockers"))),
        key=lambda r: r["standup_date"],
    )
    if not dated:
        return []

    runs: list[dict] = []
    current = [dated[0]]

    for prev, row in zip(dated, dated[1:]):
        continues = _is_next_working_day(prev["standup_date"], row["standup_date"]) and similar(
            prev.get("blockers"), row.get("blockers")
        )
        if continues:
            current.append(row)
            continue
        runs.append(current)
        current = [row]
    runs.append(current)

    return [
        {
            "days": len(run),
            "first_seen": run[0]["standup_date"],
            "last_seen": run[-1]["standup_date"],
            "text": run[-1]["blockers"],
        }
        for run in runs
        if len(run) >= min_days
    ]
