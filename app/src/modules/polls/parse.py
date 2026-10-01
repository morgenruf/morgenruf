"""Reading a poll out of what someone typed.

The quick syntax is `/morgenruf poll "Question" "Option 1" "Option 2"`. Phones
and Macs turn straight quotes into curly ones as people type, so both count.
The same limits apply to the quick syntax and to the form.
"""

from __future__ import annotations

import html
import re

MIN_OPTIONS = 2
MAX_OPTIONS = 10
MAX_QUESTION = 300
MAX_OPTION = 75

_QUOTES = '"“”'
_SEGMENT = re.compile(f"[{_QUOTES}]([^{_QUOTES}]*)[{_QUOTES}]")
_WHOLE = re.compile(f"\\s*(?:[{_QUOTES}][^{_QUOTES}]*[{_QUOTES}]\\s*)+")


def unslack(text: str) -> str:
    """Undo Slack's &amp; &lt; &gt; so the stored text is what was typed.

    Everything is escaped again when it is shown, so nothing typed here can
    turn into a mention or a link.
    """
    return html.unescape(text or "") if "&" in (text or "") else (text or "")


def parse_quick(text: str) -> tuple[str, list[str]] | None:
    """The question and options, or None when the text is not the quick syntax.

    Every part must be in quotes: anything typed outside them, an empty part,
    fewer than 2 options or more than 10 is None, so the caller can show how
    the syntax goes instead of posting a poll nobody meant.
    """
    text = unslack(text).strip()
    if not text or not _WHOLE.fullmatch(text):
        return None
    parts = [p.strip() for p in _SEGMENT.findall(text)]
    if any(not p for p in parts):
        return None
    question, options = parts[0], parts[1:]
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        return None
    return question, options


def options_from_lines(text: str) -> list[str]:
    """One option per line, blank lines ignored."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def question_error(question: str) -> str | None:
    if not (question or "").strip():
        return "Ask a question."
    if len(question) > MAX_QUESTION:
        return f"Keep the question under {MAX_QUESTION} characters."
    return None


def options_error(options: list[str]) -> str | None:
    if len(options) < MIN_OPTIONS:
        return f"Add at least {MIN_OPTIONS} options, one per line."
    if len(options) > MAX_OPTIONS:
        return f"A poll can have at most {MAX_OPTIONS} options."
    if len({o.casefold() for o in options}) != len(options):
        return "Two options are the same. Make each one different."
    if any(len(o) > MAX_OPTION for o in options):
        return f"Keep each option under {MAX_OPTION} characters."
    return None
