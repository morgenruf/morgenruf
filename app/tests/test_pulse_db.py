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
    def test_the_answer_row_has_exactly_round_question_and_value(self, cur):
        cur._fetchone = [(1,)]
        assert pdb.record_answer(7, "U1", "mood", 4) is True
        ((sql, params),) = inserts_into(cur, "pulse_answers")
        assert "(round_id, question_key, value)" in sql
        assert params == (7, "mood", 4)
        assert "U1" not in params

    def test_the_respondent_row_has_no_value(self, cur):
        cur._fetchone = [(1,)]
        pdb.record_answer(7, "U1", "mood", 4)
        ((sql, params),) = inserts_into(cur, "pulse_respondents")
        assert "ON CONFLICT DO NOTHING" in sql and "RETURNING 1" in sql
        assert 4 not in params

    def test_a_second_answer_counts_for_nothing(self, cur):
        cur._fetchone = [None]
        assert pdb.record_answer(7, "U1", "mood", 4) is False
        assert inserts_into(cur, "pulse_answers") == []

    def test_only_an_invited_person_on_an_open_round_counts(self, cur):
        cur._fetchone = [(1,)]
        pdb.record_answer(7, "U1", "mood", 4)
        ((sql, _),) = inserts_into(cur, "pulse_respondents")
        assert "closes_at > NOW()" in sql and "pulse_invites" in sql

    def test_both_rows_go_in_one_transaction(self, cur, monkeypatch):
        opened = []
        real = real_db.db_conn

        def counting():
            opened.append(1)
            return real()

        monkeypatch.setattr(pdb, "db_conn", counting)
        cur._fetchone = [(1,)]
        pdb.record_answer(7, "U1", "mood", 4)
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
        for child in ("pulse_answers", "pulse_respondents", "pulse_invites"):
            assert tables.index(child) < tables.index("pulse_rounds")
        assert "pulse_programs" in tables

    def test_children_are_reached_through_their_round(self):
        steps = dict(real_db._PURGE_STEPS)
        for child in ("pulse_answers", "pulse_respondents", "pulse_invites"):
            assert steps[child] == "round_id IN (SELECT id FROM pulse_rounds WHERE team_id = %s)"
