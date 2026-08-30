"""Work out whether a standup answer actually reports a blocker.

Two things went wrong before this existed.

The answers are stored positionally as `yesterday`, `today`, `blockers`, named
after the default questions, and `has_blockers` was computed from whatever
landed in the third slot. Schedules can set their own questions, so a standup
asking "Availability in Hours" had `4:30 Hrs` stored as a blocker and counted
as one. On the production workspace two of ten schedules were in that state.

And the check for "no blocker" was `answer.strip().lower() not in
("none", "no", "nope", "-", "n/a", "")`, which misses almost everything people
actually type. Across 589 flagged standups the most common values were `Na`,
`.`, `n`, `• None`, `na`, `NA`, `0`. The bullet case is the sharpest: the bot
tells people to write bullet points with `•`, and then the leading bullet
stopped `• None` from matching `none`.
"""

from __future__ import annotations

import re

# A question is about blockers if it says so. Deliberately narrow: a question
# that does not mention being blocked or stuck should never have its answer
# counted, which is the bug this module exists to prevent.
_BLOCKER_QUESTION = re.compile(r"block|blocker|impediment|stuck|blocked", re.I)

# Wording people actually use for "nothing is blocking me".
_NO_BLOCKER_PHRASES = frozenset(
    {
        "",
        "n",
        "na",
        "no",
        "nope",
        "none",
        "nil",
        "nothing",
        "nothing today",
        "no blocker",
        "no blockers",
        "none today",
        "not blocked",
        "nothing blocking",
        "all good",
        "all clear",
        "clear",
        "good",
        "fine",
        "ok",
        "okay",
        "nada",
        "zero",
        "x",
        "tbd",
    }
)

# Leading list markers the bot itself encourages, plus stray punctuation.
_STRIP_EDGES = re.compile(r"^[\s\-–—*•·>.,:;!]+|[\s\-–—*•·>.,:;!]+$")
_COLLAPSE = re.compile(r"\s+")

# Slack emoji shortcodes and pictographs. "No Blocker:saluting_face:" is a real
# answer from production that the phrase list missed for want of this.
_EMOJI_SHORTCODE = re.compile(r":[a-z0-9_+-]+:")
_PICTOGRAPH = re.compile("[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u2190-\u21ff]")

# Qualifiers that do not change the answer. "nothing for now" is still nothing.
_TRAILING_QUALIFIER = re.compile(
    r"\s*(?:for|as of|right)?\s*(?:now|today|yet|currently|atm|at the moment|so far|this week)\s*$",
    re.I,
)

# Answers that are only a quantity: "0", "2", "0h", "4:30 Hrs", "1.5 hours".
# These come from questions about availability, not about being blocked.
_QUANTITY_ONLY = re.compile(r"^[\d\s.:,/hms+-]*(?:h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?$", re.I)


def normalise(answer: str | None) -> str:
    """Lowercase, strip list markers and punctuation, collapse whitespace."""
    if not answer:
        return ""
    text = str(answer).replace("\r", " ").replace("\n", " ")
    text = _EMOJI_SHORTCODE.sub(" ", text)
    text = _PICTOGRAPH.sub(" ", text)
    text = _COLLAPSE.sub(" ", text)
    text = _STRIP_EDGES.sub("", text).strip().lower()
    # Drop a trailing qualifier, then tidy the edges it may have exposed.
    trimmed = _TRAILING_QUALIFIER.sub("", text)
    if trimmed:
        text = _STRIP_EDGES.sub("", trimmed).strip()
    return text


def is_blocker_question(question: str | None) -> bool:
    """True when this question is asking whether the person is blocked."""
    return bool(question) and bool(_BLOCKER_QUESTION.search(str(question)))


def reports_a_blocker(answer: str | None) -> bool:
    """True when the answer describes something actually blocking the person.

    Anything that normalises to a known way of saying "nothing", or that is
    only a quantity, is not a blocker.
    """
    text = normalise(answer)
    if not text:
        return False
    if text in _NO_BLOCKER_PHRASES:
        return False
    if _QUANTITY_ONLY.match(text):
        return False
    # "• None" and "- none." reduce to "none" above. A short answer built only
    # from repeated no-words ("no, none") is still a no.
    words = {w for w in re.split(r"[\s,/&+]+", text) if w}
    return not (words and words <= _NO_BLOCKER_PHRASES)


def find_blocker_answer(questions: list[str] | None, answers: list[str] | None) -> str | None:
    """Return the answer to this standup's blocker question, if it has one.

    Returns None when the standup does not ask about blockers, which is the
    case that used to be silently counted.
    """
    answers = answers or []
    if not questions:
        # No question list, so fall back to the historical third slot. Callers
        # that know the questions should pass them.
        return answers[2] if len(answers) > 2 else None
    for index, question in enumerate(questions):
        if is_blocker_question(question):
            return answers[index] if index < len(answers) else ""
    return None


def has_blockers(questions: list[str] | None, answers: list[str] | None) -> bool:
    """Whether this standup reports a blocker, given what it actually asked."""
    answer = find_blocker_answer(questions, answers)
    if answer is None:
        return False
    return reports_a_blocker(answer)
