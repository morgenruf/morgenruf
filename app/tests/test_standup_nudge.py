"""The private nudge for people who have not filed yet.

A DM rather than a channel post, deliberately: naming people in a channel
produces compliance through embarrassment, the answers get shorter and less
honest, and the bot becomes something the team works around.

The rules that matter are about who is *not* nudged. A reminder that ignores
someone's leave, or their explicit skip, is worse than no reminder at all.
"""

from __future__ import annotations

import inspect

from src.core import scheduler


def _source() -> str:
    return inspect.getsource(scheduler._nudge_missing)


# ── who is left alone ────────────────────────────────────────────────────────


def test_people_on_leave_are_not_nudged():
    """eligible_members drops vacation and deactivation, by construction."""
    src = _source()
    assert "eligible_members(team_id)" in src
    assert "uid in eligible" in src


def test_someone_who_skipped_today_is_not_nudged():
    assert "is_skipped_today(team_id, uid)" in _source()


def test_someone_who_already_answered_is_not_nudged():
    src = _source()
    assert "get_standups_for_schedule" in src
    assert "uid not in answered" in src


def test_only_people_on_this_standup_are_considered():
    """A workspace running ten standups must not nudge everyone for one of them."""
    src = _source()
    assert 'schedule.get("participants")' in src


def test_nothing_is_sent_when_everyone_has_filed():
    assert "if not outstanding:" in _source()


# ── whether it runs at all ───────────────────────────────────────────────────


def test_the_setting_is_re_read_when_the_job_runs():
    """Switching it off should take effect without rebuilding the scheduler."""
    assert 'schedule.get("nudge_missing")' in _source()


def test_an_inactive_standup_does_not_nudge():
    assert 'schedule.get("active")' in _source()


def test_a_deleted_standup_does_not_raise():
    assert "if not schedule" in _source()


# ── how it is sent ───────────────────────────────────────────────────────────


def test_it_is_a_direct_message_not_a_channel_post():
    """The whole point. A channel post would name people publicly."""
    src = _source()
    assert "chat_postMessage" in src
    assert "channel=user_id" in src


def test_one_persons_failure_does_not_stop_the_rest():
    src = _source()
    assert "for user_id in outstanding:" in src
    assert "except Exception as exc:" in src


def test_the_message_offers_the_way_out_as_well_as_the_way_in():
    """Telling someone only to file it makes skipping feel like disobedience."""
    src = _source()
    assert "`standup`" in src
    assert "`skip`" in src


# ── scheduling ───────────────────────────────────────────────────────────────


def test_it_is_registered_where_schedules_actually_register():
    """It was first added to register_workspace_job, which schedules do not go
    through, so the job was never created for any of them and the feature did
    nothing at all."""
    src = inspect.getsource(scheduler.register_schedule_job)
    assert "nudge_dt = datetime(2000, 1, 1, int(r_hour), int(r_minute)) - timedelta(minutes=before)" in src


def test_the_job_is_namespaced_per_schedule():
    src = inspect.getsource(scheduler.register_schedule_job)
    assert 'f"nudge_missing_{team_id}_{schedule_id}"' in src


def test_it_defaults_to_twenty_minutes():
    assert 'schedule.get("nudge_minutes_before") or 20' in inspect.getsource(scheduler.register_schedule_job)


def test_the_workspace_level_registration_does_not_claim_to_do_it():
    """Two places register jobs; only one is reached for a schedule."""
    assert "_nudge_missing" not in inspect.getsource(scheduler.register_workspace_job)
