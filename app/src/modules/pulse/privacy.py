"""The one rule every pulse read path goes through.

Results for a round, or for one question in it, are shown only once at least
MIN_GROUP people answered. Below that an average is close enough to one
person's answer to give it away. The dashboard, the API, the App Home and any
later surface read results only through db.round_results and db.trend, which
apply this.
"""

from __future__ import annotations

MIN_GROUP = 5


def visible(respondents: int) -> bool:
    """Whether a group this size may be shown."""
    return int(respondents or 0) >= MIN_GROUP


def hidden_payload(respondents: int) -> dict:
    """What a read path returns in place of results for a group too small."""
    return {"hidden": True, "respondents": int(respondents or 0), "needed": MIN_GROUP}
