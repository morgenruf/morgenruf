"""The three engagement toggles have to change what Slack receives.

They were added with the settings page. A control with no column behind it
saves nothing and reports success, which is the defect this codebase spent a
day removing from the standup settings, so these assert the whole path: the
column exists, the API persists it, and the message changes.
"""

from __future__ import annotations

import pathlib
import re

from src.modules.connect import blocks as cb

APP = pathlib.Path(__file__).resolve().parent.parent
CONNECT = APP / "src/modules/connect"


class TestStorageExists:
    def test_the_columns_are_added_with_safe_defaults(self):
        sql = (CONNECT / "migrations/044_program_engagement.sql").read_text()
        for col, default in (("suggest_times", "TRUE"), ("use_icebreaker", "TRUE"), ("post_stats", "FALSE")):
            assert re.search(rf"{col} BOOLEAN NOT NULL DEFAULT {default}", sql), col

    def test_update_program_will_persist_them(self):
        allowed = (CONNECT / "db.py").read_text()
        block = allowed[allowed.index("def update_program") : allowed.index("def update_program") + 1400]
        for col in ("suggest_times", "use_icebreaker", "post_stats"):
            assert f'"{col}"' in block, f"{col} would be dropped by the allowlist"

    def test_the_form_sends_them(self):
        markup = (APP / "src/core/templates/dashboard.html").read_text()
        body = markup[markup.index("async function saveConnectSettings") :][:1400]
        for col in ("suggest_times", "use_icebreaker", "post_stats"):
            assert col in body, f"{col} is never sent, so the toggle does nothing"

    def test_the_form_loads_them_defaulting_on(self):
        markup = (APP / "src/core/templates/dashboard.html").read_text()
        assert "p.suggest_times !== false" in markup
        assert "p.use_icebreaker !== false" in markup


class TestTheMessageActuallyChanges:
    def _msg(self, **kw):
        return cb.intro_message(["U1", "U2"], seed=3, program_id=1, match_id=9, **kw)

    def test_the_icebreaker_can_be_turned_off(self):
        _, on = self._msg(with_icebreaker=True)
        _, off = self._msg(with_icebreaker=False)
        text_on = " ".join(b.get("text", {}).get("text", "") for b in on)
        text_off = " ".join(b.get("text", {}).get("text", "") for b in off)
        assert "Something to open with" in text_on
        assert "Something to open with" not in text_off

    def test_turning_it_off_removes_its_divider_too(self):
        # A divider with nothing under it is a visible seam.
        _, off = self._msg(with_icebreaker=False)
        assert off[-1]["type"] != "divider"

    def test_it_defaults_on_so_existing_programmes_are_unchanged(self):
        _, blocks = self._msg()
        text = " ".join(b.get("text", {}).get("text", "") for b in blocks)
        assert "Something to open with" in text

    def test_the_overflow_survives_either_way(self):
        for flag in (True, False):
            _, blocks = self._msg(with_icebreaker=flag)
            assert any((b.get("accessory") or {}).get("type") == "overflow" for b in blocks)


class TestRoundStatsMessage:
    def test_it_counts_only_the_people_who_answered(self):
        # 1 of 5 pairs answering and meeting is not "20% met".
        text, blocks = cb.round_stats_message(met=1, answered=1, pairings=5)
        body = " ".join(b.get("text", {}).get("text", "") for b in blocks if b.get("text"))
        assert "5 pairs were introduced" in body
        assert "1 of the 1 who answered met up" in body

    def test_with_nobody_answering_it_says_so_rather_than_zero_percent(self):
        _, blocks = cb.round_stats_message(met=0, answered=0, pairings=4)
        body = " ".join(b.get("text", {}).get("text", "") for b in blocks if b.get("text"))
        assert "Nobody has said yet" in body
        assert "0%" not in body

    def test_one_pairing_reads_as_singular(self):
        _, blocks = cb.round_stats_message(met=1, answered=1, pairings=1)
        body = " ".join(b.get("text", {}).get("text", "") for b in blocks if b.get("text"))
        assert "1 pair were introduced" in body or "1 pair " in body


class TestGatingInTheJob:
    def test_times_are_skipped_when_the_programme_says_so(self):
        src = (CONNECT / "jobs.py").read_text()
        assert 'want_times = program.get("suggest_times", True) is not False' in src
        assert "if want_times else []" in src

    def test_reading_timezones_is_skipped_too(self):
        # No point loading the roster's zones to build times nobody wants.
        src = (CONNECT / "jobs.py").read_text()
        assert "_member_timezones(team_id) if want_times else {}" in src

    def test_stats_are_posted_after_the_round_closes_not_before(self):
        src = (CONNECT / "jobs.py").read_text()
        close = src[src.index("def close_round") :][:1600]
        assert 'set_round_state(round_id, "closed")' in close
        assert close.index('set_round_state(round_id, "closed")') < close.index("_post_round_stats")

    def test_a_failed_stats_post_cannot_stop_a_round_closing(self):
        src = (CONNECT / "jobs.py").read_text()
        fn = src[src.index("def _post_round_stats") :][:1400]
        assert "except Exception" in fn
