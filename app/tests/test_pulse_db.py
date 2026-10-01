"""Pulse storage: one answer per person per question, and none of it named."""

from __future__ import annotations

import pytest
import src.core.db as real_db
from src.modules.pulse import db as pdb


@pytest.fixture
def cur(fake_cursor_db, monkeypatch):
    monkeypatch.setattr(pdb, "db_conn", real_db.db_conn)
    return fake_cursor_db


def inserts_into(cur, table):
    return [(sql, params) for sql, params in cur.calls if sql.startswith(f"INSERT INTO {table}")]


class TestRecordAnswer:
    def test_the_tally_row_has_round_question_and_value_and_no_person(self, cur):
        cur._fetchone = [(1,)]
        assert pdb.record_answer(7, "U1", "mood", 4) is True
        ((sql, params),) = inserts_into(cur, "pulse_tallies")
        assert "(round_id, question_key, value, count)" in sql
        assert "ON CONFLICT (round_id, question_key, value) DO UPDATE SET count = pulse_tallies.count + 1" in sql
        assert params == (7, "mood", 4)

    def test_the_respondent_row_has_no_value(self, cur):
        cur._fetchone = [(1,)]
        pdb.record_answer(7, "U1", "mood", 4)
        ((sql, params),) = inserts_into(cur, "pulse_respondents")
        assert "ON CONFLICT DO NOTHING" in sql and "RETURNING 1" in sql
        assert 4 not in params

    def test_a_second_answer_counts_for_nothing(self, cur):
        cur._fetchone = [None]
        assert pdb.record_answer(7, "U1", "mood", 4) is False
        assert inserts_into(cur, "pulse_tallies") == []

    def test_only_an_invited_person_on_an_open_round_counts(self, cur):
        cur._fetchone = [(1,)]
        pdb.record_answer(7, "U1", "mood", 4)
        ((sql, _),) = inserts_into(cur, "pulse_respondents")
        assert "closes_at > NOW()" in sql and "pulse_invites" in sql

    def test_the_claim_and_the_count_are_two_transactions(self, monkeypatch):
        """Written together, both rows would carry the same xmin, and anyone
        with the database could join the person to the value through it."""
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        from tests.support import FakeCursor

        transactions = []

        @contextmanager
        def db_conn():
            cur = FakeCursor(fetchone=[(1,)])
            conn = MagicMock()
            conn.cursor.return_value = cur
            yield conn
            # db_conn commits on a clean exit; record what each one committed.
            transactions.append([sql for sql, _ in cur.calls])

        monkeypatch.setattr(pdb, "db_conn", db_conn)
        assert pdb.record_answer(7, "U1", "mood", 4) is True
        assert len(transactions) == 2
        claim, count = transactions
        assert any(sql.startswith("INSERT INTO pulse_respondents") for sql in claim)
        assert not any("pulse_tallies" in sql for sql in claim)
        assert any(sql.startswith("INSERT INTO pulse_tallies") for sql in count)
        assert not any("pulse_respondents" in sql for sql in count)

    def test_nothing_is_counted_when_the_claim_fails(self, monkeypatch):
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        from tests.support import FakeCursor

        opened = []

        @contextmanager
        def db_conn():
            cur = FakeCursor(fetchone=[None])
            conn = MagicMock()
            conn.cursor.return_value = cur
            opened.append(cur)
            yield conn

        monkeypatch.setattr(pdb, "db_conn", db_conn)
        assert pdb.record_answer(7, "U1", "mood", 4) is False
        assert len(opened) == 1

    @pytest.mark.parametrize("key,value", [("mood", 0), ("mood", 6), ("enps", 11), ("comment", 3)])
    def test_out_of_range_is_refused_before_any_write(self, cur, key, value):
        assert pdb.record_answer(7, "U1", key, value) is False
        assert cur.calls == []


class TestRounds:
    def test_a_round_is_created_once_per_day(self, cur):
        pdb.create_round("T1", "2026-10-01", "2026-10-04T14:00:00+00:00")
        sql, _ = cur.calls[0]
        assert "ON CONFLICT (team_id, sent_on) DO NOTHING" in sql

    def test_the_first_round_and_every_fourth_ask_enps(self, cur):
        pdb.create_round("T1", "2026-10-01", "2026-10-04T14:00:00+00:00")
        assert "MOD((SELECT COUNT(*) FROM pulse_rounds WHERE team_id = %s), 4) = 0" in cur.calls[0][0]

    def test_a_reminder_is_claimed_once(self, cur):
        assert pdb.claim_reminder(3) is False
        assert "reminded_at IS NULL" in cur.calls[0][0]


class TestPurge:
    def test_children_before_the_rounds(self):
        tables = list(real_db.PURGED_TABLES)
        for child in ("pulse_tallies", "pulse_respondents", "pulse_invites"):
            assert tables.index(child) < tables.index("pulse_rounds")
        assert "pulse_programs" in tables

    def test_children_are_reached_through_their_round(self):
        steps = dict(real_db._PURGE_STEPS)
        for child in ("pulse_tallies", "pulse_respondents", "pulse_invites"):
            assert steps[child] == "round_id IN (SELECT id FROM pulse_rounds WHERE team_id = %s)"
