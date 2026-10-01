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
    def test_there_is_no_table_with_one_row_per_answer(self):
        sql = MIGRATION.read_text()
        assert "pulse_answers" not in sql
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql)
        assert set(tables) == {"pulse_programs", "pulse_rounds", "pulse_respondents", "pulse_invites", "pulse_tallies"}

    def test_tallies_have_no_user_and_no_time(self):
        columns = table_columns("pulse_tallies")
        assert set(columns) == {"round_id", "question_key", "value", "count"}
        assert not any("TIME" in t or "DATE" in t for t in columns.values())
        assert "PRIMARY KEY (round_id, question_key, value)" in MIGRATION.read_text()

    def test_respondents_have_no_value_and_no_time(self):
        columns = table_columns("pulse_respondents")
        assert set(columns) == {"round_id", "user_id", "question_key"}

    def test_no_free_text_column_anywhere_an_answer_lives(self):
        assert table_columns("pulse_tallies")["value"].startswith("SMALLINT")


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

    def test_enps_math_from_counts(self):
        assert questions.enps_score_from_counts({10: 2, 9: 1, 8: 1, 7: 1, 6: 1, 0: 1}) == 14
        assert questions.enps_score_from_counts({}) is None

    def test_unknown_question_takes_nothing(self):
        assert not questions.valid("comment", 1)


@pytest.fixture
def cur(fake_cursor_db, monkeypatch):
    monkeypatch.setattr(pdb, "db_conn", real_db.db_conn)
    return fake_cursor_db


def result_script(cur, respondents, mood, enps=(), invited=12, includes_enps=True, closed=True):
    """A round as storage holds it. Closed rounds carry their stored count."""
    if closed:
        cur._fetchone = [(1, "T1", invited, includes_enps, "2026-10-01", True, respondents)]
    else:
        cur._fetchone = [(1, "T1", invited, includes_enps, "2026-10-01", False, None), (respondents,)]
    counts = {}
    for key, values in (("mood", mood), ("enps", enps)):
        for v in values:
            counts[(key, v)] = counts.get((key, v), 0) + 1
    cur._fetchall = [[(key, v, n) for (key, v), n in counts.items()]]


TEN_MOODS = [5, 4, 3, 2, 1, 5, 4, 3, 2, 1]
TEN_ENPS = [10, 10, 9, 8, 7, 6, 0, 10, 9, 5]


class TestRoundResults:
    def test_four_respondents_is_hidden_with_no_numbers(self, cur):
        result_script(cur, 4, [5, 4, 3, 2])
        result = pdb.round_results(1)
        assert result["hidden"] is True and result["respondents"] == 4 and result["needed"] == 5
        assert result["mood_avg"] is None and result["mood_dist"] is None and result["enps"] is None

    def test_answers_are_not_even_read_for_a_hidden_round(self, cur):
        result_script(cur, 4, [5, 4, 3, 2])
        pdb.round_results(1)
        assert not any("FROM pulse_tallies" in sql for sql, _ in cur.calls)

    def test_an_open_round_shows_nothing_however_many_answered(self, cur):
        """Refreshing an open round's results would show each new answer move them."""
        result_script(cur, 12, TEN_MOODS + [3, 3], enps=TEN_ENPS, closed=False)
        result = pdb.round_results(1)
        assert result["hidden"] is True and result["open"] is True and result["respondents"] == 12
        assert result["mood_avg"] is None and result["mood_dist"] is None and result["enps"] is None
        assert not any("FROM pulse_tallies" in sql for sql, _ in cur.calls)

    def test_five_to_nine_show_the_average_only(self, cur):
        result_script(cur, 5, [5, 4, 3, 2, 1], enps=[10, 10, 9, 8, 0])
        result = pdb.round_results(1)
        assert result["hidden"] is False
        assert result["mood_avg"] == 3.0
        assert result["mood_dist"] is None and result["enps"] is None

    def test_ten_show_the_breakdown_and_enps(self, cur):
        result_script(cur, 10, TEN_MOODS, enps=TEN_ENPS)
        result = pdb.round_results(1)
        assert result["mood_avg"] == 3.0
        assert result["mood_dist"] == [2, 2, 2, 2, 2]
        assert result["enps"] == 20  # 5 promoters and 3 detractors out of 10

    def test_a_question_with_fewer_than_five_answers_stays_hidden(self, cur):
        result_script(cur, 6, [5, 4, 3, 2, 1, 3], enps=[10, 0])
        result = pdb.round_results(1)
        assert result["mood_avg"] is not None
        assert result["enps"] is None

    def test_the_thresholds_live_next_to_each_other(self):
        assert privacy.MIN_GROUP == 5 and privacy.MIN_DETAIL == 10

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

    def test_trend_keeps_an_open_round_to_its_counts(self, cur, monkeypatch):
        cur._fetchall = [[(3,)]]
        monkeypatch.setattr(
            pdb,
            "round_results",
            lambda round_id: {
                "round_id": 3,
                "sent_on": "2026-10-08",
                "respondents": 12,
                "invited": 14,
                "hidden": True,
                "open": True,
                "needed": 5,
                "mood_avg": None,
            },
        )
        assert pdb.trend("T1") == [
            {"sent_on": "2026-10-08", "respondents": 12, "invited": 14, "hidden": True, "needed": 5, "open": True}
        ]
