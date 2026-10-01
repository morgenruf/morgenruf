"""The quick poll syntax and the limits the form shares with it."""

from __future__ import annotations

import pytest
from src.modules.polls.parse import options_error, options_from_lines, parse_quick, question_error


class TestQuickSyntax:
    def test_straight_quotes(self):
        assert parse_quick('"Lunch?" "Pizza" "Sushi"') == ("Lunch?", ["Pizza", "Sushi"])

    def test_curly_quotes(self):
        assert parse_quick("“Lunch?” “Pizza” “Sushi”") == ("Lunch?", ["Pizza", "Sushi"])

    def test_mixed_quotes_and_spacing(self):
        assert parse_quick('  “Lunch?"   "Pizza”"Sushi" ') == ("Lunch?", ["Pizza", "Sushi"])

    def test_one_option_is_not_a_poll(self):
        assert parse_quick('"Lunch?" "Pizza"') is None

    def test_eleven_options_is_too_many(self):
        assert parse_quick('"Q" ' + " ".join(f'"o{i}"' for i in range(11))) is None

    def test_ten_options_is_fine(self):
        found = parse_quick('"Q" ' + " ".join(f'"o{i}"' for i in range(10)))
        assert found is not None and len(found[1]) == 10

    @pytest.mark.parametrize(
        "text",
        ['Lunch? "Pizza" "Sushi"', '"Lunch?" "Pizza" "Sushi" please', '"Lunch?" Pizza "Sushi"', "", "   "],
    )
    def test_text_outside_quotes_is_refused(self, text):
        assert parse_quick(text) is None

    def test_an_empty_part_is_refused(self):
        assert parse_quick('"Lunch?" "" "Sushi"') is None

    def test_slack_entities_are_undone(self):
        assert parse_quick('"Fish &amp; chips?" "Yes" "&lt;no&gt;"') == ("Fish & chips?", ["Yes", "<no>"])


class TestLimits:
    def test_options_one_per_line_blank_lines_ignored(self):
        assert options_from_lines("Pizza\n\n  Sushi  \n") == ["Pizza", "Sushi"]

    def test_question_required_and_bounded(self):
        assert question_error("")
        assert question_error("x" * 301)
        assert question_error("Lunch?") is None

    @pytest.mark.parametrize(
        "options",
        [["a"], [str(i) for i in range(11)], ["Pizza", "pizza"], ["a", "x" * 76]],
    )
    def test_bad_options(self, options):
        assert options_error(options)

    def test_good_options(self):
        assert options_error(["a", "b"]) is None
