"""Tests for blocker detection.

The values here are not invented. They are the answers most often stored in the
`blockers` column on the production workspace, where 589 standups were flagged
as blocked and the ten commonest values were `Na`, `.`, `n`, `• None`, `na`,
`NA`, `0`, `2`, `1`, `0h`.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from blockers import (  # noqa: E402
    find_blocker_answer,
    has_blockers,
    is_blocker_question,
    normalise,
    reports_a_blocker,
)

DEFAULT_Q = ["What did you complete yesterday?", "What are you working on today?", "Any blockers?"]
AVAILABILITY_Q = ["❇️ Previous day work", "➡️ Plan for today", "⏳ Availability in Hours"]


class TestRealProductionValues:
    """Every one of these was counted as a blocker before this module existed."""

    def test_the_ten_commonest_flagged_values_are_not_blockers(self):
        for value in ["Na", ".", "n", "• None", "na", "NA", "0", "2", "1", "0h"]:
            assert reports_a_blocker(value) is False, value

    def test_the_bullet_case(self):
        """The bot asks for bullets, then the old check failed to strip them."""
        assert reports_a_blocker("None") is False
        assert reports_a_blocker("• None") is False
        assert reports_a_blocker("- none.") is False

    def test_an_emoji_shortcode_does_not_hide_the_answer(self):
        assert reports_a_blocker("No Blocker:saluting_face:") is False

    def test_a_trailing_qualifier_does_not_change_the_answer(self):
        for value in ["nothing for now", "• nothing for now", "none as of now", "No blockers today"]:
            assert reports_a_blocker(value) is False, value


class TestRealBlockersStillCount:
    def test_plain_english_blockers(self):
        for value in [
            "waiting on staging creds",
            "CI flake blocking release",
            "• Blocked on review from Sam",
            "need access to prod DB",
            "no access to the cluster",
            "nothing works, the cluster is down",
        ]:
            assert reports_a_blocker(value) is True, value

    def test_a_qualifier_inside_a_real_blocker_is_not_stripped_away(self):
        """ "blocked for now on review" must not reduce to "blocked"."""
        assert reports_a_blocker("blocked for now on review") is True

    def test_no_at_the_start_of_a_real_sentence(self):
        """ "No access to prod" contains "no" but is a blocker."""
        assert reports_a_blocker("No access to prod") is True


class TestQuestionDecidesWhetherToLook:
    def test_availability_answers_are_never_blockers(self):
        for value in ["4:30 Hrs", "8", "0h", "6 hours", "1.5 hrs"]:
            assert has_blockers(AVAILABILITY_Q, ["x", "y", value]) is False, value

    def test_the_same_answer_under_a_blocker_question_is_read_normally(self):
        assert has_blockers(DEFAULT_Q, ["x", "y", "waiting on creds"]) is True
        assert has_blockers(DEFAULT_Q, ["x", "y", "Na"]) is False

    def test_a_standup_with_no_blocker_question_never_reports_one(self):
        questions = ["Previous day work", "Plan for today", "Availability in Hours"]
        assert has_blockers(questions, ["a", "b", "anything at all here"]) is False

    def test_the_blocker_question_is_found_wherever_it_sits(self):
        questions = ["Any impediments?", "What did you do?", "What is next?"]
        assert find_blocker_answer(questions, ["stuck on auth", "b", "c"]) == "stuck on auth"
        assert has_blockers(questions, ["stuck on auth", "b", "c"]) is True

    def test_question_wording_variants(self):
        for q in ["Any blockers?", "Any blockers or impediments?", "Anything blocking you?", "Are you stuck?"]:
            assert is_blocker_question(q) is True, q
        for q in ["⏳ Availability in Hours", "What are you working on today?", "Mood?", ""]:
            assert is_blocker_question(q) is False, q


class TestEdges:
    def test_missing_and_empty_inputs(self):
        assert reports_a_blocker(None) is False
        assert reports_a_blocker("") is False
        assert reports_a_blocker("   ") is False
        assert has_blockers(None, None) is False
        assert has_blockers(DEFAULT_Q, []) is False

    def test_without_questions_it_falls_back_to_the_third_answer(self):
        """Legacy callers that cannot supply the questions still work."""
        assert find_blocker_answer(None, ["a", "b", "stuck"]) == "stuck"
        assert has_blockers(None, ["a", "b", "stuck"]) is True
        assert has_blockers(None, ["a", "b", "Na"]) is False

    def test_fewer_answers_than_questions(self):
        assert has_blockers(DEFAULT_Q, ["only one"]) is False

    def test_normalise_is_idempotent(self):
        for value in ["• None", "Na", "  nothing for now  ", "No Blocker:tada:"]:
            once = normalise(value)
            assert normalise(once) == once, value

    def test_a_multi_word_answer_of_only_no_words(self):
        assert reports_a_blocker("no, none") is False
        assert reports_a_blocker("none / nil") is False
