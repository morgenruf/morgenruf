"""The rules every pulse read path goes through.

Results are shown only for a round that has closed: while it is open, each
refresh would show the numbers move by one person's answer. A closed round,
or one question in it, shows its average only once at least MIN_GROUP people
answered, and the breakdown and eNPS only from MIN_DETAIL, because in a small
group a distribution names people where an average does not. The dashboard,
the API, the App Home and any later surface read results only through
db.round_results and db.trend, which apply this.
"""

from __future__ import annotations

MIN_GROUP = 5
MIN_DETAIL = 10


def visible(respondents: int) -> bool:
    """Whether a group this size may be shown."""
    return int(respondents or 0) >= MIN_GROUP


def detailed(respondents: int) -> bool:
    """Whether a group this size may see the breakdown and eNPS, not only the average."""
    return int(respondents or 0) >= MIN_DETAIL


def hidden_payload(respondents: int, open_round: bool = False) -> dict:
    """What a read path returns in place of results: for a group too small, or a round still open."""
    payload = {"hidden": True, "respondents": int(respondents or 0), "needed": MIN_GROUP}
    if open_round:
        payload["open"] = True
    return payload
