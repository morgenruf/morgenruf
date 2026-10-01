"""The pulse anonymity promises, each pinned.

1. An answer is stored with no user id and no timestamp.
2. Who answered is kept apart, with no value.
3. Nothing is shown for a group under five.
4. Buttons only, no free text.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import src.core.db as real_db
from src.modules.pulse import db as pdb
from src.modules.pulse import privacy, questions

MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "src/modules/pulse/migrations/065_pulse.sql"


def table_columns(name: str) -> dict[str, str]:
    sql = re.sub(r"/\*.*?\*/", "", MIGRATION.read_text(), flags=re.S)
    body = sql[sql.index(f"CREATE TABLE IF NOT EXISTS {name} ") :]
    body = body[body.index("(") + 1 : body.index("\n);")]
    columns = {}
    for line in body.splitlines():
        parts = line.strip().rstrip(",").split()
        if parts and parts[0] not in ("PRIMARY", "UNIQUE"):
            columns[parts[0]] = " ".join(parts[1:]).upper()
    return columns


class TestTheSchema:
    def test_answers_have_no_user_and_no_time(self):
        columns = table_columns("pulse_answers")
        assert set(columns) == {"id", "round_id", "question_key", "value"}
        assert not any("TIME" in t or "DATE" in t for t in columns.values())
        assert "gen_random_uuid()" in columns["id"].lower()

    def test_respondents_have_no_value_and_no_time(self):
        columns = table_columns("pulse_respondents")
        assert set(columns) == {"round_id", "user_id", "question_key"}

    def test_no_free_text_column_anywhere_an_answer_lives(self):
        assert table_columns("pulse_answers")["value"].startswith("SMALLINT")


class TestTheGate:
    def test_five_is_the_minimum(self):
        assert privacy.MIN_GROUP == 5
        assert not privacy.visible(4)
        assert privacy.visible(5)

    def test_hidden_payload(self):
        assert privacy.hidden_payload(3) == {"hidden": True, "respondents": 3, "needed": 5}


class TestQuestions:
    def test_mood_is_one_to_five(self):
        assert list(questions.values("mood")) == [1, 2, 3, 4, 5]
        assert questions.MOOD_LABELS == ("Rough", "Meh", "Okay", "Good", "Great")

    def test_enps_is_zero_to_ten(self):
        assert list(questions.values("enps")) == list(range(11))

    def test_enps_every_fourth_round_starting_with_the_first(self):
        assert [n for n in range(1, 10) if questions.includes_enps(n)] == [1, 5, 9]

    def test_enps_math(self):
        assert questions.enps_score([10, 10, 9, 8, 7, 6, 0]) == 14

    def test_unknown_question_takes_nothing(self):
        assert not questions.valid("comment", 1)


@pytest.fixture
def cur(fake_cursor_db, monkeypatch):
    monkeypatch.setattr(pdb, "db_conn", real_db.db_conn)
    return fake_cursor_db


def result_script(cur, respondents, mood, enps=(), invited=8, includes_enps=True):
    cur._fetchone = [
        (1, "T1", invited, includes_enps, "2026-10-01"),
        (respondents,),
    ]
    rows = [("mood", v) for v in mood] + [("enps", v) for v in enps]
    cur._fetchall = [rows]


class TestRoundResults:
    def test_four_respondents_is_hidden_with_no_numbers(self, cur):
        result_script(cur, 4, [5, 4, 3, 2])
        result = pdb.round_results(1)
        assert result["hidden"] is True and result["respondents"] == 4 and result["needed"] == 5
        assert result["mood_avg"] is None and result["mood_dist"] is None and result["enps"] is None

    def test_answers_are_not_even_read_for_a_hidden_round(self, cur):
        result_script(cur, 4, [5, 4, 3, 2])
        pdb.round_results(1)
        assert not any("FROM pulse_answers" in sql for sql, _ in cur.calls)

    def test_five_respondents_shows_the_team_average(self, cur):
        result_script(cur, 5, [5, 4, 3, 2, 1], enps=[10, 10, 9, 8, 0])
        result = pdb.round_results(1)
        assert result["hidden"] is False
        assert result["mood_avg"] == 3.0
        assert result["mood_dist"] == [1, 1, 1, 1, 1]
        assert result["enps"] == 40

    def test_a_question_with_fewer_than_five_answers_stays_hidden(self, cur):
        result_script(cur, 6, [5, 4, 3, 2, 1, 3], enps=[10, 0])
        result = pdb.round_results(1)
        assert result["mood_avg"] is not None
        assert result["enps"] is None

    def test_trend_drops_every_number_from_a_hidden_round(self, cur, monkeypatch):
        cur._fetchall = [[(2,), (1,)]]
        results = {
            1: {"round_id": 1, "sent_on": "2026-09-24", "respondents": 3, "invited": 9, "hidden": True},
            2: {
                "round_id": 2,
                "sent_on": "2026-10-01",
                "respondents": 6,
                "invited": 9,
                "hidden": False,
                "mood_avg": 3.5,
                "mood_dist": [0, 1, 2, 2, 1],
                "enps": None,
                "includes_enps": False,
            },
        }
        monkeypatch.setattr(pdb, "round_results", lambda round_id: dict(results[round_id]))
        trend = pdb.trend("T1")
        assert trend[0] == {"sent_on": "2026-09-24", "respondents": 3, "invited": 9, "hidden": True, "needed": 5}
        assert trend[1]["mood_avg"] == 3.5
