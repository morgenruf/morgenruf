"""The pulse questions. Buttons only: there is no free text in pulse."""

from __future__ import annotations

MOOD = "mood"
ENPS = "enps"

MOOD_TEXT = "How was work for you this week?"
MOOD_LABELS = ("Rough", "Meh", "Okay", "Good", "Great")
ENPS_TEXT = "How likely are you to recommend working here to a friend?"

# eNPS is asked every fourth round, starting with the first.
ENPS_EVERY = 4


def values(question_key: str) -> range:
    if question_key == MOOD:
        return range(1, len(MOOD_LABELS) + 1)
    if question_key == ENPS:
        return range(0, 11)
    return range(0)


def valid(question_key: str, value: int) -> bool:
    return value in values(question_key)


def round_questions(includes_enps: bool) -> tuple[str, ...]:
    """The questions in a round, in the order they are asked."""
    return (MOOD, ENPS) if includes_enps else (MOOD,)


def includes_enps(round_number: int) -> bool:
    """Round 1, 5, 9 and so on."""
    return round_number % ENPS_EVERY == 1


def enps_score(answers: list[int]) -> int | None:
    """Promoters (9, 10) minus detractors (0 to 6), as a whole percentage."""
    if not answers:
        return None
    promoters = sum(1 for v in answers if v >= 9)
    detractors = sum(1 for v in answers if v <= 6)
    return round(100 * (promoters - detractors) / len(answers))


def enps_score_from_counts(counts: dict[int, int]) -> int | None:
    """enps_score, from how many people picked each value."""
    total = sum(counts.values())
    if not total:
        return None
    promoters = sum(n for v, n in counts.items() if v >= 9)
    detractors = sum(n for v, n in counts.items() if v <= 6)
    return round(100 * (promoters - detractors) / total)
