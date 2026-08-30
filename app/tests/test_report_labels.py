"""Reports must label answers with the questions that were actually asked.

The page hardcoded "Yesterday", "Today" and "Blockers". Those are the default
questions, not the only ones. A schedule asking "Availability in Hours" third
had answers like "4:30 Hrs" printed under a red Blockers heading, which is the
display half of the bug `blockers.py` fixed on the computing side.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import dashboard  # noqa: E402

DEFAULT_Q = ["What did you do yesterday?", "What will you do today?", "Any blockers?"]
AVAILABILITY_Q = ["Previous day work", "Plan for today", "Availability in Hours"]


def _sched(sid, participants, questions, active=True):
    return {"id": sid, "participants": participants, "questions": questions, "active": active}


def _run(schedules, standups):
    with patch.object(dashboard.db, "get_standup_schedules", return_value=schedules):
        dashboard._attach_questions("T1", standups)
    return standups


class TestAttachQuestions:
    def test_the_schedule_id_on_the_row_wins(self):
        rows = _run(
            [_sched(1, ["U1"], DEFAULT_Q), _sched(2, ["U1"], AVAILABILITY_Q)],
            [{"user_id": "U1", "schedule_id": 2}],
        )
        assert rows[0]["questions"] == AVAILABILITY_Q

    def test_without_a_schedule_id_it_falls_back_to_the_only_schedule(self):
        rows = _run([_sched(1, ["U1"], AVAILABILITY_Q)], [{"user_id": "U1"}])
        assert rows[0]["questions"] == AVAILABILITY_Q

    def test_two_schedules_that_disagree_produce_no_label(self):
        """Someone in a morning and an evening standup asking different things.

        Guessing is what caused the bug; leaving it unlabelled keeps the
        generic headings rather than an attractive wrong answer.
        """
        rows = _run(
            [_sched(1, ["U1"], DEFAULT_Q), _sched(2, ["U1"], AVAILABILITY_Q)],
            [{"user_id": "U1"}],
        )
        assert rows[0]["questions"] is None

    def test_two_schedules_that_agree_are_not_ambiguous(self):
        rows = _run(
            [_sched(1, ["U1"], DEFAULT_Q), _sched(2, ["U1"], DEFAULT_Q)],
            [{"user_id": "U1"}],
        )
        assert rows[0]["questions"] == DEFAULT_Q

    def test_a_paused_schedule_does_not_decide_the_labels(self):
        rows = _run(
            [_sched(1, ["U1"], DEFAULT_Q), _sched(2, ["U1"], AVAILABILITY_Q, active=False)],
            [{"user_id": "U1"}],
        )
        assert rows[0]["questions"] == DEFAULT_Q

    def test_but_a_paused_schedule_still_resolves_its_own_id(self):
        """History outlives the schedule being paused."""
        rows = _run([_sched(9, ["U1"], AVAILABILITY_Q, active=False)], [{"user_id": "U1", "schedule_id": 9}])
        assert rows[0]["questions"] == AVAILABILITY_Q

    def test_someone_in_no_schedule_gets_no_label(self):
        rows = _run([_sched(1, ["U1"], DEFAULT_Q)], [{"user_id": "U2"}])
        assert rows[0]["questions"] is None

    def test_an_empty_list_of_standups_is_fine(self):
        assert _run([_sched(1, ["U1"], DEFAULT_Q)], []) == []

    def test_a_failing_schedule_lookup_leaves_the_rows_alone(self):
        rows = [{"user_id": "U1"}]
        with patch.object(dashboard.db, "get_standup_schedules", side_effect=RuntimeError("no db")):
            dashboard._attach_questions("T1", rows)
        assert "questions" not in rows[0]

    def test_a_schedule_with_no_questions_is_skipped(self):
        rows = _run([_sched(1, ["U1"], [])], [{"user_id": "U1"}])
        assert rows[0]["questions"] is None


class TestResolveChannelNames:
    """Mentions of channels the bot has not joined rendered as raw ids."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        dashboard._CHANNEL_NAME_CACHE.clear()
        yield
        dashboard._CHANNEL_NAME_CACHE.clear()

    def _client(self, names):
        client = MagicMock()
        client.conversations_info.side_effect = lambda channel: {"channel": {"name": names[channel]}}
        return client

    def test_a_mention_in_an_answer_is_resolved(self):
        rows = [{"yesterday": "shipped to <#C0B3JSAQWPL>"}]
        with patch("slack_sdk.WebClient", return_value=self._client({"C0B3JSAQWPL": "deploys"})):
            assert dashboard._resolve_channel_names("xoxb", rows) == {"C0B3JSAQWPL": "deploys"}

    def test_the_piped_form_slack_also_sends(self):
        rows = [{"today": "see <#C123|old-name>"}]
        with patch("slack_sdk.WebClient", return_value=self._client({"C123": "new-name"})):
            assert dashboard._resolve_channel_names("xoxb", rows) == {"C123": "new-name"}

    def test_every_answer_field_is_scanned(self):
        rows = [{"yesterday": "<#C1>", "today": "<#C2>", "blockers": "<#C3>"}]
        names = {"C1": "one", "C2": "two", "C3": "three"}
        with patch("slack_sdk.WebClient", return_value=self._client(names)):
            assert dashboard._resolve_channel_names("xoxb", rows) == names

    def test_no_mentions_makes_no_slack_call(self):
        with patch("slack_sdk.WebClient") as wc:
            assert dashboard._resolve_channel_names("xoxb", [{"today": "nothing here"}]) == {}
        wc.assert_not_called()

    def test_the_cache_stops_a_second_lookup(self):
        rows = [{"today": "<#C1>"}]
        client = self._client({"C1": "one"})
        with patch("slack_sdk.WebClient", return_value=client):
            dashboard._resolve_channel_names("xoxb", rows)
            dashboard._resolve_channel_names("xoxb", rows)
        assert client.conversations_info.call_count == 1

    def test_a_channel_that_cannot_be_read_is_skipped_not_fatal(self):
        client = MagicMock()
        client.conversations_info.side_effect = RuntimeError("channel_not_found")
        rows = [{"today": "<#CPRIVATE>"}]
        with patch("slack_sdk.WebClient", return_value=client):
            assert dashboard._resolve_channel_names("xoxb", rows) == {}

    def test_one_bad_channel_does_not_stop_the_others(self):
        client = MagicMock()
        client.conversations_info.side_effect = [
            RuntimeError("nope"),
            {"channel": {"name": "good"}},
        ]
        rows = [{"today": "<#C1> and <#C2>"}]
        with patch("slack_sdk.WebClient", return_value=client):
            assert dashboard._resolve_channel_names("xoxb", rows) == {"C2": "good"}

    def test_the_number_of_lookups_is_bounded(self):
        """A standup full of mentions must not become dozens of Slack calls."""
        mentions = " ".join(f"<#C{i:05d}>" for i in range(60))
        client = MagicMock()
        client.conversations_info.return_value = {"channel": {"name": "x"}}
        with patch("slack_sdk.WebClient", return_value=client):
            dashboard._resolve_channel_names("xoxb", [{"today": mentions}])
        assert client.conversations_info.call_count == 25
