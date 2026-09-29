"""Legacy timezone names must never stop a schedule from firing.

Production incident 2026-09-29: a standup saved with "Asia/Calcutta" (what
Chrome's Intl API reports) could not be resolved by zoneinfo in the image,
because Debian no longer ships the tz database's backward compatibility links
and the tzdata package was not installed. APScheduler converts every pytz
timezone through zoneinfo, so registering that schedule raised, and the raise
aborted the startup loop and every DB sync at the same row.

The `debian_tz` fixture recreates that environment: a system tz directory with
canonical zones only, and no tzdata package.
"""

from __future__ import annotations

import importlib
import pathlib
import re
import sys
import zoneinfo
from datetime import datetime, timezone
from importlib import resources
from unittest.mock import MagicMock

import pytest

from tests.support import patch_modules

for _name in ("pytz", "slack_sdk"):
    if isinstance(sys.modules.get(_name), MagicMock):
        del sys.modules[_name]

_prior_session_store = sys.modules.get("src.core.session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["src.core.session_store"] = _ss_mock

_had_scheduler = "scheduler" in sys.modules
import src.core.scheduler as sched_mod  # noqa: E402

if _had_scheduler:
    sched_mod = importlib.reload(sched_mod)

if _prior_session_store is not None:
    sys.modules["src.core.session_store"] = _prior_session_store
else:
    sys.modules.pop("src.core.session_store", None)

import pytz  # noqa: E402
from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from src.core.timezones import LEGACY_TZ_ALIASES, canonical_tz  # noqa: E402

_APP = pathlib.Path(__file__).resolve().parent.parent
MIGRATION = _APP / "src" / "core" / "migrations" / "057_canonical_timezones.sql"

# Canonical zones the tests below need from the stripped tz directory.
_CANONICAL_ZONES = ("UTC", "Etc/UTC", "Europe/Amsterdam", "Asia/Kolkata", "America/New_York")


@pytest.fixture
def debian_tz(tmp_path, monkeypatch):
    """zoneinfo as the production image had it: canonical names only, no tzdata."""
    import tzlocal

    zones = set(_CANONICAL_ZONES)
    local = str(tzlocal.get_localzone())
    if "/" in local or local == "UTC":
        zones.add(local)
    for name in zones:
        data = resources.files("tzdata.zoneinfo").joinpath(*name.split("/")).read_bytes()
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    for module in [m for m in sys.modules if m == "tzdata" or m.startswith("tzdata.")]:
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setitem(sys.modules, "tzdata", None)
    zoneinfo.reset_tzpath([str(tmp_path)])
    zoneinfo.ZoneInfo.clear_cache()
    yield
    zoneinfo.reset_tzpath()
    zoneinfo.ZoneInfo.clear_cache()


@pytest.fixture
def no_canonicalising(monkeypatch):
    """Send names to the trigger as stored, the way the scheduler did before the fix."""
    monkeypatch.setattr(sched_mod, "canonical_tz", lambda name: name)


def _schedule_row(schedule_id, team_id="T1", tz="Europe/Amsterdam"):
    return {
        "id": schedule_id,
        "team_id": team_id,
        "bot_token": "xoxb-test",
        "name": f"Standup {schedule_id}",
        "channel_id": "C1",
        "schedule_time": "10:00",
        "schedule_tz": tz,
        "schedule_days": "mon,tue,wed,thu,fri",
        "questions": [],
        "participants": ["U1"],
        "reminder_minutes": 0,
        "weekend_reminder": False,
        "report_time": None,
        "active": True,
    }


def _make_db(schedules=(), installations=(), configs=None):
    db = MagicMock()
    db.get_all_active_schedules.return_value = list(schedules)
    db.get_all_installations.return_value = list(installations)
    configs = configs or {}
    db.get_workspace_config.side_effect = lambda team_id: configs.get(team_id, {"active": True})
    return db


@pytest.fixture
def scheduler_state():
    sched_mod._synced_schedule_fps.clear()
    sched_mod._synced_workspace_fps.clear()
    yield
    sched_mod._scheduler = None
    sched_mod._synced_schedule_fps.clear()
    sched_mod._synced_workspace_fps.clear()


# ── The environment really reproduces the incident ──────────────────────────


def test_fixture_reproduces_the_missing_link(debian_tz):
    assert zoneinfo.ZoneInfo("Asia/Kolkata").key == "Asia/Kolkata"
    with pytest.raises(zoneinfo.ZoneInfoNotFoundError):
        zoneinfo.ZoneInfo("Asia/Calcutta")


# ── The tzdata package resolves legacy names on its own ─────────────────────


def test_tzdata_is_a_pinned_runtime_dependency():
    requirements = (_APP / "requirements.txt").read_text().splitlines()
    assert any(re.fullmatch(r"tzdata==\d{4}\.\d+", line.strip()) for line in requirements)


@pytest.mark.parametrize("legacy", ["Asia/Calcutta", "US/Eastern", "Asia/Saigon", "Europe/Kiev"])
def test_legacy_names_resolve_from_tzdata_without_a_system_database(legacy, monkeypatch):
    zoneinfo.reset_tzpath([])
    zoneinfo.ZoneInfo.clear_cache()
    try:
        assert zoneinfo.ZoneInfo(legacy).key == legacy
    finally:
        zoneinfo.reset_tzpath()
        zoneinfo.ZoneInfo.clear_cache()


# ── canonical_tz ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Asia/Calcutta", "Asia/Kolkata"),
        (" Asia/Calcutta ", "Asia/Kolkata"),
        ("US/Eastern", "America/New_York"),
        ("Europe/Kiev", "Europe/Kyiv"),
        ("Asia/Saigon", "Asia/Ho_Chi_Minh"),
        ("Asia/Kolkata", "Asia/Kolkata"),
        ("UTC", "UTC"),
        (" Europe/Berlin ", "Europe/Berlin"),
        ("", ""),
        (None, None),
    ],
)
def test_canonical_tz(raw, expected):
    assert canonical_tz(raw) == expected


@pytest.mark.parametrize(("legacy", "canonical"), sorted(LEGACY_TZ_ALIASES.items()))
def test_every_alias_points_at_the_same_zone(legacy, canonical):
    """Each target is a real zone, not itself an alias, with the same offsets."""
    assert canonical not in LEGACY_TZ_ALIASES
    target = zoneinfo.ZoneInfo(canonical)
    source = pytz.timezone(legacy)
    for instant in (datetime(2026, 1, 15, 12, tzinfo=timezone.utc), datetime(2026, 7, 15, 12, tzinfo=timezone.utc)):
        assert instant.astimezone(target).utcoffset() == instant.astimezone(source).utcoffset()


# ── Scheduling survives a bad row ───────────────────────────────────────────


def test_legacy_name_registers_even_without_the_link(debian_tz, scheduler_state):
    scheduler = BackgroundScheduler()
    sched_mod.register_schedule_job(scheduler, _schedule_row(38, team_id="T0C526JGDRA", tz="Asia/Calcutta"))
    job = scheduler.get_job("schedule_T0C526JGDRA_38")
    assert job is not None
    assert str(job.trigger.timezone) == "Asia/Kolkata"


def test_build_scheduler_skips_a_bad_row_and_registers_the_rest(debian_tz, no_canonicalising, scheduler_state):
    rows = [_schedule_row(1), _schedule_row(38, team_id="T2", tz="Asia/Calcutta"), _schedule_row(40, team_id="T3")]
    with patch_modules({"src.core.db": _make_db(schedules=rows)}):
        scheduler = sched_mod.build_scheduler([])

    assert scheduler.get_job("schedule_T1_1") is not None
    assert scheduler.get_job("schedule_T3_40") is not None
    assert scheduler.get_job("schedule_T2_38") is None
    # Left out so the DB sync tries it again.
    assert ("T2", 38) not in sched_mod._synced_schedule_fps
    assert ("T3", 40) in sched_mod._synced_schedule_fps


def test_build_scheduler_skips_a_bad_workspace_and_registers_the_rest(debian_tz, no_canonicalising, scheduler_state):
    good = {"channel_id": "C1", "schedule_time": "09:00", "schedule_tz": "Europe/Amsterdam"}
    bad = {**good, "schedule_tz": "US/Eastern"}
    with patch_modules({"src.core.db": _make_db()}):
        scheduler = sched_mod.build_scheduler([("T1", "x", bad), ("T2", "x", good)])

    assert scheduler.get_job("standup_T2") is not None
    assert "T2" in sched_mod._synced_workspace_fps
    assert "T1" not in sched_mod._synced_workspace_fps


def test_sync_skips_a_bad_row_and_retries_it_next_pass(debian_tz, no_canonicalising, scheduler_state, monkeypatch):
    sched_mod._scheduler = BackgroundScheduler()
    rows = [_schedule_row(38, team_id="T2", tz="Asia/Calcutta"), _schedule_row(40, team_id="T3")]
    installations = [{"team_id": "T2", "bot_token": "x"}, {"team_id": "T3", "bot_token": "x"}]
    db = _make_db(schedules=rows, installations=installations)
    with patch_modules({"src.core.db": db}):
        sched_mod._sync_jobs_from_db()

    assert sched_mod._scheduler.get_job("schedule_T3_40") is not None
    assert sched_mod._scheduler.get_job("digest_T3") is not None
    assert sched_mod._scheduler.get_job("schedule_T2_38") is None
    # Workspace level jobs for the team after the bad row still sync.
    assert sched_mod._scheduler.get_job("digest_T2") is not None

    # Once the name resolves (canonicalising back on), the next pass registers it.
    monkeypatch.setattr(sched_mod, "canonical_tz", canonical_tz)
    with patch_modules({"src.core.db": db}):
        sched_mod._sync_jobs_from_db()
    assert sched_mod._scheduler.get_job("schedule_T2_38") is not None


def test_sync_skips_a_bad_workspace_and_registers_the_rest(debian_tz, no_canonicalising, scheduler_state):
    sched_mod._scheduler = BackgroundScheduler()
    configs = {
        "T1": {"active": True, "channel_id": "C1", "schedule_time": "09:00", "schedule_tz": "US/Eastern"},
        "T2": {"active": True, "channel_id": "C1", "schedule_time": "09:00", "schedule_tz": "UTC"},
    }
    installations = [{"team_id": "T1", "bot_token": "x"}, {"team_id": "T2", "bot_token": "x"}]
    with patch_modules({"src.core.db": _make_db(installations=installations, configs=configs)}):
        sched_mod._sync_jobs_from_db()

    assert sched_mod._scheduler.get_job("standup_T2") is not None
    assert sched_mod._scheduler.get_job("standup_T1") is None
    assert sched_mod._synced_workspace_fps["T1"] == sched_mod._UNREGISTERED_FP


def test_connect_skips_a_programme_it_cannot_schedule(debian_tz, monkeypatch):
    import src.modules.connect.db as cdb
    import src.modules.connect.jobs as cjobs

    monkeypatch.setattr(cjobs, "canonical_tz", lambda name: name)
    base = {"team_id": "T1", "day_of_week": 0, "hour": 10, "minute": 0}
    programs = [{**base, "id": 1, "timezone": "Asia/Calcutta"}, {**base, "id": 2, "timezone": "Asia/Kolkata"}]
    monkeypatch.setattr(cdb, "active_programs", lambda: programs)

    keys = {job.key for job in cjobs.plan_jobs({"team_id": "T1"})}
    assert "round:2" in keys
    assert "round:1" not in keys
    assert "followups" in keys


# ── Migration 057 ───────────────────────────────────────────────────────────


def _migration_pairs() -> dict[str, str]:
    sql = MIGRATION.read_text()
    values = sql.split("INSERT INTO tz_legacy_aliases", 1)[1].split(";", 1)[0]
    return dict(re.findall(r"\('([^']+)',\s*'([^']+)'\)", values))


def test_migration_rewrites_exactly_the_aliases_the_app_knows():
    assert _migration_pairs() == LEGACY_TZ_ALIASES


def test_migration_covers_every_timezone_column():
    sql = MIGRATION.read_text()
    for table, column in (
        ("workspace_config", "schedule_tz"),
        ("members", "tz"),
        ("standup_schedules", "schedule_tz"),
        ("connect_programs", "timezone"),
        ("celebration_settings", "timezone"),
    ):
        assert f"('{table}', '{column}')" in sql


def test_migration_number_is_not_shared():
    names = [p.name for p in (_APP / "src").rglob("migrations/*.sql")]
    assert [n for n in names if n.startswith("057_")] == [MIGRATION.name]
