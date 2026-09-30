"""Coffee chat dates are on the programme's calendar, not the server's.

date.today() is the server's day (UTC in production). For a programme in
Auckland or Toronto that is a different day for part of every day, so the
App Home named the wrong "next introduction" and snoozes started a day off.
"""

from datetime import date
from unittest.mock import MagicMock, patch


def test_home_uses_each_programmes_own_day():
    import src.modules.connect.home as home

    program = {"id": 1, "enabled": True, "channel_id": "C1", "interval_weeks": 1, "timezone": "Pacific/Auckland"}
    cdb = MagicMock()
    cdb.get_programs.return_value = [program]
    cdb.personal_state.return_value = {"state": "in", "until": None}
    upcoming = MagicMock(return_value=date(2026, 10, 5))
    with (
        patch("src.modules.connect.db.get_programs", cdb.get_programs),
        patch("src.modules.connect.db.personal_state", cdb.personal_state),
        patch("src.modules.connect.rounds.programme_today", return_value=date(2026, 9, 30)) as today,
        patch("src.modules.connect.rounds.upcoming_round_date", upcoming),
    ):
        home.home_blocks("T1", "U1")
    today.assert_called_once_with(program)
    assert upcoming.call_args.args[1] == date(2026, 9, 30)


def test_optout_query_takes_the_programme_day():
    from contextlib import contextmanager

    import src.modules.connect.db as cdb

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def fake_conn():
        yield conn

    with patch.object(cdb, "db_conn", fake_conn):
        cdb.optout_user_ids("T1", 1, date(2026, 9, 30))
    assert cur.execute.call_args.args[1] == ("T1", 1, date(2026, 9, 30))
