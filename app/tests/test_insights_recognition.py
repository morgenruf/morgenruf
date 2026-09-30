"""The "Showing up, without recognition" card on the Insights page.

A fresh workspace with standups and no kudos at all was told "Everyone has
been recognised". The list only admitted people with eight or more standups in
the window, so on day one it was empty, and the page read an empty list as
everyone having been thanked. The endpoint now lists every contributor who has
not been thanked and says how many contributors there were, so the page can
tell "nobody filed anything" from "everyone who filed was thanked".
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

TODAY = dt.date(2026, 9, 28)


def _row(user_id, standups, kudos, name=None):
    return {
        "user_id": user_id,
        "real_name": name or user_id,
        "standups": standups,
        "last_standup": TODAY,
        "kudos": kudos,
    }


@pytest.fixture()
def insights():
    """Return a caller that runs /dashboard/api/insights over the given contributor rows."""
    import src.modules.insights.db as idb
    from flask import Flask
    from src.modules.insights import MODULE

    def run(contributors):
        flask_app = Flask(__name__)
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret"
        MODULE.register_routes(flask_app)
        client = flask_app.test_client()
        with client.session_transaction() as sess:
            sess["team_id"] = "T1"
            sess["user_id"] = "U1"
        with (
            patch.object(idb, "contributor_recognition", return_value=[dict(r) for r in contributors]),
            patch.object(idb, "blocker_rows", return_value={}),
        ):
            response = client.get("/dashboard/api/insights")
        assert response.status_code == 200
        return response.get_json()

    return run


def test_a_workspace_with_no_kudos_lists_every_contributor(insights):
    """Two people filed one and two standups, nobody has any kudos: both are listed."""
    body = insights([_row("U2", 2, 0), _row("U1", 1, 0)])
    assert body["contributors"] == 2
    assert [r["user_id"] for r in body["unrecognised"]] == ["U2", "U1"]
    assert body["unrecognised"][0]["last_standup"] == TODAY.isoformat()


def test_people_already_thanked_are_left_out(insights):
    body = insights([_row("U1", 9, 3), _row("U2", 4, 0)])
    assert body["contributors"] == 2
    assert [r["user_id"] for r in body["unrecognised"]] == ["U2"]


def test_the_list_is_empty_only_when_every_contributor_was_thanked(insights):
    body = insights([_row("U1", 9, 3), _row("U2", 4, 1)])
    assert body["contributors"] == 2
    assert body["unrecognised"] == []


def test_no_contributors_is_reported_as_zero_not_as_everyone_thanked(insights):
    body = insights([])
    assert body["contributors"] == 0
    assert body["unrecognised"] == []


def _cursor_returning(rows):
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


def test_the_query_no_longer_filters_by_kudos_or_standup_count():
    import src.modules.insights.db as idb

    conn, cur = _cursor_returning([])
    with patch.object(idb, "db_conn", return_value=conn):
        idb.contributor_recognition("T1", days=30)
    sql, params = cur.execute.call_args.args
    assert "min_standups" not in sql
    assert "= 0" not in sql
    assert params["team"] == "T1" and params["days"] == 30
    # The window ends on the workspace's local day, not the database's UTC date.
    assert "CURRENT_DATE" not in sql
    assert "today" in params


def test_the_mcp_helper_still_means_consistent_and_unthanked():
    """The MCP tool keeps its meaning: at least `min_standups`, and no kudos."""
    import src.modules.insights.db as idb

    rows = [_row("U1", 12, 0), _row("U2", 12, 2), _row("U3", 3, 0)]
    with patch.object(idb, "contributor_recognition", return_value=rows):
        assert [r["user_id"] for r in idb.unrecognised_contributors("T1", days=30, min_standups=8)] == ["U1"]
        assert [r["user_id"] for r in idb.unrecognised_contributors("T1", days=30, min_standups=1)] == ["U1", "U3"]


def test_a_failed_query_reads_as_no_contributors():
    import src.modules.insights.db as idb

    with patch.object(idb, "db_conn", side_effect=RuntimeError("down")):
        assert idb.contributor_recognition("T1") == []


def test_windows_end_on_the_workspaces_local_day():
    from datetime import date

    import src.modules.insights.db as idb

    conn, cur = _cursor_returning([])
    with (
        patch.object(idb, "db_conn", return_value=conn),
        patch.object(idb, "workspace_local_today", return_value=date(2026, 9, 30)),
    ):
        idb.contributor_recognition("T1", days=30)
        assert cur.execute.call_args.args[1]["today"] == date(2026, 9, 30)
        idb.blocker_rows("T1", days=21)
        assert cur.execute.call_args.args[1] == ("T1", date(2026, 9, 30), 21)
