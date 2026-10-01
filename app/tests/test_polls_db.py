"""Polls storage, and the promise that a closed anonymous vote names no one."""

from __future__ import annotations

import pathlib
import re

import pytest
import src.core.db as real_db
from src.modules.polls import db as pdb

MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "src/modules/polls/migrations/064_polls.sql"


@pytest.fixture
def cur(fake_cursor_db, monkeypatch):
    """The FakeCursor, reached through polls.db's own db_conn binding."""
    monkeypatch.setattr(pdb, "db_conn", real_db.db_conn)
    return fake_cursor_db


def sqls(cur) -> list[str]:
    return [sql for sql, _ in cur.calls]


class TestTheSchema:
    def test_votes_have_no_column_beyond_the_key(self):
        sql = re.sub(r"/\*.*?\*/", "", MIGRATION.read_text(), flags=re.S)
        body = sql[sql.index("CREATE TABLE IF NOT EXISTS poll_votes") :]
        body = body[body.index("(") + 1 : body.index(");")]
        columns = {
            line.split()[0] for line in body.splitlines() if line.strip() and not line.strip().startswith("PRIMARY")
        }
        assert columns == {"poll_id", "option_idx", "voter_key"}

    def test_the_salt_lives_in_its_own_table(self):
        """Backups skip poll_salts' data, so a restored database cannot recompute a voter key."""
        sql = re.sub(r"/\*.*?\*/", "", MIGRATION.read_text(), flags=re.S)
        polls = sql[sql.index("CREATE TABLE IF NOT EXISTS polls ") :]
        polls = polls[: polls.index(");")]
        assert "salt" not in polls
        salts = sql[sql.index("CREATE TABLE IF NOT EXISTS poll_salts") :]
        salts = salts[: salts.index(");")]
        assert "poll_id     BIGINT PRIMARY KEY REFERENCES polls(id) ON DELETE CASCADE" in salts
        assert "salt        BYTEA NOT NULL" in salts

    def test_polls_belong_to_an_installation(self):
        assert "REFERENCES installations(team_id) ON DELETE CASCADE" in MIGRATION.read_text()


class TestVoterKey:
    POLL = {"anonymous": True, "salt": b"s" * 32}

    def test_anonymous_is_a_hex_hmac_not_the_user(self):
        key = pdb.voter_key(self.POLL, "U1")
        assert re.fullmatch(r"[0-9a-f]{64}", key)
        assert "U1" not in key

    def test_anonymous_is_stable_for_the_same_salt(self):
        assert pdb.voter_key(self.POLL, "U1") == pdb.voter_key(dict(self.POLL), "U1")

    def test_anonymous_differs_per_person_and_per_poll(self):
        assert pdb.voter_key(self.POLL, "U1") != pdb.voter_key(self.POLL, "U2")
        assert pdb.voter_key(self.POLL, "U1") != pdb.voter_key({"anonymous": True, "salt": b"t" * 32}, "U1")

    def test_named_is_the_user_id(self):
        assert pdb.voter_key({"anonymous": False, "salt": None}, "U1") == "U1"

    def test_anonymous_without_a_salt_is_refused_not_the_user_id(self):
        with pytest.raises(ValueError):
            pdb.voter_key({"anonymous": True, "salt": None}, "U1")


class TestCreate:
    def test_anonymous_gets_a_fresh_32_byte_salt_in_poll_salts(self, cur):
        cur._fetchone = [(7,), (8,)]
        assert pdb.create_poll("T1", "U1", "C1", "Q?", ["a", "b"], True, False, False, None) == 7
        pdb.create_poll("T1", "U1", "C1", "Q?", ["a", "b"], True, False, False, None)
        salts = [params for sql, params in cur.calls if sql.startswith("INSERT INTO poll_salts")]
        assert [p[0] for p in salts] == [7, 8]
        first, second = (bytes(p[1]) for p in salts)
        assert len(first) == 32 and first != second
        assert all("salt" not in sql for sql, _ in cur.calls if sql.startswith("INSERT INTO polls"))

    def test_the_salt_goes_in_with_the_poll(self, cur, monkeypatch):
        opened = []
        real = real_db.db_conn

        def counting():
            opened.append(1)
            return real()

        monkeypatch.setattr(pdb, "db_conn", counting)
        cur._fetchone = [(7,)]
        pdb.create_poll("T1", "U1", "C1", "Q?", ["a", "b"], True, False, False, None)
        assert len(opened) == 1

    def test_named_has_no_salt(self, cur):
        cur._fetchone = [(7,)]
        pdb.create_poll("T1", "U1", "C1", "Q?", ["a", "b"], False, False, False, None)
        assert not any(sql.startswith("INSERT INTO poll_salts") for sql, _ in cur.calls)

    def test_a_poll_is_read_with_its_salt_joined_in(self, cur):
        pdb.get_poll(5)
        assert "LEFT JOIN poll_salts" in cur.calls[0][0]


class TestClose:
    def test_close_deletes_the_salt_and_only_once(self, cur):
        cur._fetchone = [(1,)]
        assert pdb.close_poll(5) is True
        (update, params), (delete, delete_params) = cur.calls
        assert "closed_at = NOW()" in update and "closed_at IS NULL" in update and params == (5,)
        assert "salt" not in update
        assert delete == "DELETE FROM poll_salts WHERE poll_id = %s" and delete_params == (5,)

    def test_close_of_a_closed_poll_says_so(self, cur):
        assert pdb.close_poll(5) is False
        assert not any("poll_salts" in sql for sql, _ in cur.calls)


class TestToggle:
    def test_one_choice_removes_other_options_before_the_insert(self, cur):
        cur._fetchone = [(None,)]
        cur.rowcount = 0
        assert pdb.toggle_vote(5, 1, "K", multiple=False) is True
        statements = sqls(cur)
        other = next(i for i, s in enumerate(statements) if "option_idx <> %s" in s)
        insert = next(i for i, s in enumerate(statements) if s.startswith("INSERT INTO poll_votes"))
        assert other < insert
        assert "ON CONFLICT DO NOTHING" in statements[insert]

    def test_it_is_one_transaction(self, cur, monkeypatch):
        opened = []
        real = real_db.db_conn

        def counting():
            opened.append(1)
            return real()

        monkeypatch.setattr(pdb, "db_conn", counting)
        cur._fetchone = [(None,)]
        cur.rowcount = 0
        pdb.toggle_vote(5, 1, "K", multiple=False)
        assert len(opened) == 1

    def test_same_option_again_removes_it(self, cur):
        cur._fetchone = [(None,)]
        cur.rowcount = 1
        assert pdb.toggle_vote(5, 1, "K", multiple=False) is True
        assert not any(s.startswith("INSERT") for s in sqls(cur))

    def test_multiple_keeps_the_other_options(self, cur):
        cur._fetchone = [(None,)]
        cur.rowcount = 0
        pdb.toggle_vote(5, 1, "K", multiple=True)
        assert not any("option_idx <> %s" in s for s in sqls(cur))
        assert any(s.startswith("INSERT INTO poll_votes") for s in sqls(cur))

    def test_concurrent_clicks_by_one_voter_are_serialised(self, cur):
        cur._fetchone = [(None,)]
        cur.rowcount = 0
        pdb.toggle_vote(5, 1, "K", multiple=False)
        assert any("FOR SHARE" in s for s in sqls(cur))
        assert any("pg_advisory_xact_lock" in s for s in sqls(cur))

    def test_a_closed_poll_takes_no_vote(self, cur):
        from datetime import datetime, timezone

        cur._fetchone = [(datetime.now(timezone.utc),)]
        assert pdb.toggle_vote(5, 1, "K", multiple=False) is False
        assert not any(s.startswith(("INSERT", "DELETE")) for s in sqls(cur))


class TestReads:
    def test_tally_fills_every_option(self, cur):
        cur._fetchone = [(3,)]
        cur._fetchall = [[(0, 2), (2, 5)]]
        assert pdb.tally(5) == [2, 0, 5]

    def test_voters_refuses_an_anonymous_poll(self, cur):
        cur._fetchone = [(True,)]
        with pytest.raises(ValueError):
            pdb.voters(5)
        assert not any("poll_votes" in s for s in sqls(cur))

    def test_voters_of_a_named_poll(self, cur):
        cur._fetchone = [(False,)]
        cur._fetchall = [[(0, "U1"), (0, "U2"), (1, "U3")]]
        assert pdb.voters(5) == {0: ["U1", "U2"], 1: ["U3"]}

    def test_list_never_reads_the_salt(self, cur):
        pdb.list_polls("T1")
        assert "salt" not in cur.calls[0][0]


class TestPurge:
    def test_votes_and_salts_go_before_their_polls(self):
        tables = list(real_db.PURGED_TABLES)
        assert tables.index("poll_votes") < tables.index("polls")
        assert tables.index("poll_salts") < tables.index("polls")

    def test_votes_are_reached_through_their_poll(self):
        steps = dict(real_db._PURGE_STEPS)
        assert steps["poll_votes"] == "poll_id IN (SELECT id FROM polls WHERE team_id = %s)"
        assert steps["poll_salts"] == "poll_id IN (SELECT id FROM polls WHERE team_id = %s)"
        assert steps["polls"] == "team_id = %s"


class TestRedraw:
    POLL = {
        "id": 5,
        "team_id": "T1",
        "created_by": "U1",
        "channel_id": "C1",
        "message_ts": "1.0",
        "question": "Q",
        "options": ["a", "b"],
        "anonymous": False,
        "multiple": False,
        "hide_results": False,
        "salt": None,
        "closes_at": None,
        "closed_at": "now",
        "created_at": None,
    }

    def test_the_lock_comes_before_the_reads_on_one_connection(self, cur):
        cur._fetchone = [dict(self.POLL)]
        cur._fetchall = [[{"option_idx": 0, "voter_key": "U2"}, {"option_idx": 0, "voter_key": "U3"}]]
        drawn = []
        assert pdb.redraw(5, lambda poll, counts, names: drawn.append((poll, counts, names))) is True
        sqls = [sql for sql, _ in cur.calls]
        assert "pg_advisory_xact_lock" in sqls[0] and "polls:redraw:" in cur.calls[0][1][0]
        assert sqls[1].startswith("SELECT") and "FROM polls" in sqls[1]
        poll, counts, names = drawn[0]
        assert poll["closed_at"] == "now" and counts == [2, 0] and names == {0: ["U2", "U3"]}

    def test_an_anonymous_poll_draws_no_names(self, cur):
        cur._fetchone = [{**self.POLL, "anonymous": True, "salt": b"s" * 32}]
        cur._fetchall = [[{"option_idx": 1, "voter_key": "a" * 64}]]
        drawn = []
        pdb.redraw(5, lambda poll, counts, names: drawn.append((counts, names)))
        assert drawn == [([0, 1], None)]

    def test_a_missing_poll_draws_nothing(self, cur):
        assert pdb.redraw(5, lambda *a: (_ for _ in ()).throw(AssertionError("drew"))) is False


def test_the_auto_close_job_only_counts_polls_with_a_closing_time(cur):
    pdb.open_poll_count("T1")
    assert "closes_at IS NOT NULL" in cur.calls[0][0]
