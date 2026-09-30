"""Celebrations: who is celebrated when, what is said, and that nothing posts twice.

Dates used below (2026): 25 September is a Friday. 23 December is a
Wednesday, 24 and 25 December a Thursday and Friday, 26 and 27 the weekend.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
import src.core.modules as core_modules
import src.core.workspace_calendar as wc
from src.core.workspace_calendar import Calendar
from src.modules.celebrations import handlers, jobs, messages, rules
from src.modules.celebrations.rules import ANNIVERSARY, BIRTHDAY, Celebration, Honoree, Person


# The database modules are imported when a test runs, never at collection:
# importing src.core.db here would bind the real module onto src.core before
# test_dashboard installs its stub, and that file's tests would then reach a
# real, unconfigured pool.
def _cdb():
    import src.modules.celebrations.db as module

    return module


def _core_db():
    import src.core.db as module

    return module


FRI = date(2026, 9, 25)
SAT = date(2026, 9, 26)
SUN = date(2026, 9, 27)
MON = date(2026, 9, 28)
MON_FRI = Calendar()
SUN_THU = Calendar(working_days=wc.parse_working_days("sun,mon,tue,wed,thu"))
MONDAY_OFF = Calendar(holidays={MON: "Company day"})
CHRISTMAS = Calendar(
    holidays={
        date(2026, 12, 24): "Christmas Eve",
        date(2026, 12, 25): "Christmas Day",
        date(2026, 12, 26): "Boxing Day",
    }
)


def born(uid, day, name=""):
    return Person(uid, name, birth_month=day.month, birth_day=day.day)


def joined(uid, start, name=""):
    return Person(uid, name, start_date=start)


# ── Rules ───────────────────────────────────────────────────────────────────


class TestGrouping:
    def test_one_post_per_kind_per_day(self):
        people = [born("U1", FRI, "Priya"), born("U2", FRI, "Tom"), joined("U3", date(2023, 9, 25), "Ana")]
        posts = rules.due(people, MON_FRI, FRI)
        assert [(p.kind, p.day, p.user_ids) for p in posts] == [
            (BIRTHDAY, FRI, ["U1", "U2"]),
            (ANNIVERSARY, FRI, ["U3"]),
        ]

    def test_people_are_listed_alphabetically(self):
        posts = rules.due([born("U9", FRI, "Zoe"), born("U1", FRI, "Adam")], MON_FRI, FRI)
        assert posts[0].user_ids == ["U1", "U9"]

    def test_either_kind_can_be_switched_off(self):
        people = [born("U1", FRI), joined("U2", date(2020, 9, 25))]
        assert [p.kind for p in rules.due(people, MON_FRI, FRI, birthdays=False)] == [ANNIVERSARY]
        assert [p.kind for p in rules.due(people, MON_FRI, FRI, anniversaries=False)] == [BIRTHDAY]


class TestNonWorkingDays:
    def test_friday_covers_the_weekend(self):
        people = [born("U_SAT", SAT), born("U_SUN", SUN), born("U_MON", MON)]
        posts = rules.due(people, MON_FRI, FRI)
        assert [(p.day, p.user_ids) for p in posts] == [(SAT, ["U_SAT"]), (SUN, ["U_SUN"])]

    def test_nothing_is_posted_on_the_weekend(self):
        assert rules.due([born("U_SAT", SAT)], MON_FRI, SAT) == []
        assert rules.due([born("U_SUN", SUN)], MON_FRI, SUN) == []

    def test_monday_does_not_repeat_the_weekend(self):
        posts = rules.due([born("U_SUN", SUN), born("U_MON", MON)], MON_FRI, MON)
        assert [p.user_ids for p in posts] == [["U_MON"]]

    def test_a_monday_holiday_is_posted_on_friday(self):
        people = [born("U_MON", MON)]
        assert [(p.day, p.user_ids) for p in rules.due(people, MONDAY_OFF, FRI)] == [(MON, ["U_MON"])]
        assert rules.due(people, MONDAY_OFF, MON) == []

    def test_a_run_of_christmas_holidays_is_posted_before_it(self):
        people = [born(f"U{d}", date(2026, 12, d)) for d in (24, 25, 26, 27, 28)]
        posts = rules.due(people, CHRISTMAS, date(2026, 12, 23))
        assert [p.day.day for p in posts] == [24, 25, 26, 27]
        for day in (24, 25, 26, 27):
            assert rules.due(people, CHRISTMAS, date(2026, 12, day)) == []
        assert [p.day.day for p in rules.due(people, CHRISTMAS, date(2026, 12, 28))] == [28]

    def test_sunday_to_thursday_week(self):
        fri, sat, sun = date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4)
        thu = date(2026, 10, 1)
        people = [born("U_FRI", fri), born("U_SAT", sat), born("U_SUN", sun)]
        assert [p.day for p in rules.due(people, SUN_THU, thu)] == [fri, sat]
        assert [p.day for p in rules.due(people, SUN_THU, sun)] == [sun]
        assert rules.due(people, SUN_THU, fri) == []


class TestDates:
    def test_29_february_is_celebrated_on_28_february_in_other_years(self):
        leapling = Person("U1", birth_month=2, birth_day=29)
        assert rules.is_birthday(leapling, date(2027, 2, 28))
        assert not rules.is_birthday(leapling, date(2028, 2, 28))
        assert rules.is_birthday(leapling, date(2028, 2, 29))

    def test_anniversaries_under_one_year_are_skipped(self):
        assert rules.anniversary_years(joined("U1", date(2026, 9, 25)), FRI) is None
        assert rules.due([joined("U1", date(2026, 9, 25))], MON_FRI, FRI) == []

    def test_a_future_start_date_has_no_anniversary(self):
        assert rules.anniversary_years(joined("U1", date(2027, 9, 25)), FRI) is None

    def test_years_are_counted(self):
        assert rules.anniversary_years(joined("U1", date(2025, 9, 25)), FRI) == 1
        assert rules.anniversary_years(joined("U1", date(2016, 9, 25)), FRI) == 10

    def test_a_29_february_start_date(self):
        assert rules.anniversary_years(joined("U1", date(2024, 2, 29)), date(2027, 2, 28)) == 3

    def test_upcoming_lists_each_post_with_its_day(self):
        people = [born("U_SAT", SAT)]
        plan = rules.upcoming(people, MON_FRI, date(2026, 9, 22), days=7)
        assert [(posted_on, c.day) for posted_on, c in plan] == [(FRI, SAT)]


# ── Messages ────────────────────────────────────────────────────────────────


def bday(day, *people):
    return Celebration(BIRTHDAY, day, tuple(Honoree(u, n) for u, n in people))


def anniv(day, *people):
    return Celebration(ANNIVERSARY, day, tuple(Honoree(u, n, y) for u, n, y in people))


class TestMessages:
    """The design's texts, word for word."""

    def test_one_birthday_today(self):
        text = messages.celebration_text(bday(FRI, ("U1", "Priya")), FRI, MON_FRI)
        assert text == "🎂 Today is <@U1>'s birthday!\nWishing you a lovely day, Priya. 💛"

    def test_a_birthday_double(self):
        text = messages.celebration_text(bday(FRI, ("U1", "Priya"), ("U2", "Tom")), FRI, MON_FRI)
        assert text == "🎂 Today is a birthday double: <@U1> and <@U2>!\nWishing you both a lovely day. 💛"

    def test_three_or_more(self):
        text = messages.celebration_text(bday(FRI, ("U1", "A"), ("U2", "B"), ("U3", "C")), FRI, MON_FRI)
        assert text.startswith("🎂 Today is the birthday of <@U1>, <@U2> and <@U3>!")
        assert "Happy birthday to all of you" in text

    def test_three_or_more_early(self):
        text = messages.celebration_text(bday(SUN, ("U1", "A"), ("U2", "B"), ("U3", "C")), FRI, MON_FRI)
        assert "Happy birthday to all of you" in text

    def test_saturday_is_tomorrow(self):
        text = messages.celebration_text(bday(SAT, ("U1", "Priya")), FRI, MON_FRI)
        assert text == "🎂 Tomorrow is <@U1>'s birthday!\nOff for the weekend, so let's celebrate early. 🎈"

    def test_sunday_by_name(self):
        text = messages.celebration_text(bday(SUN, ("U1", "Priya")), FRI, MON_FRI)
        assert text.startswith("🎂 On Sunday it's <@U1>'s birthday!")

    def test_a_monday_holiday(self):
        text = messages.celebration_text(bday(MON, ("U1", "Priya")), FRI, MONDAY_OFF)
        assert text == "🎂 On Monday it's <@U1>'s birthday!\nIt's a day off, so let's celebrate early. 🎈"

    def test_christmas_by_date(self):
        text = messages.celebration_text(bday(date(2026, 12, 25), ("U1", "Priya")), date(2026, 12, 23), CHRISTMAS)
        assert text.startswith("🎂 On 25 December it's <@U1>'s birthday!")
        assert "It's a day off" in text

    def test_a_three_year_anniversary(self):
        text = messages.celebration_text(anniv(FRI, ("U1", "Tom", 3)), FRI, MON_FRI)
        assert text == "🎉 Today is <@U1>'s 3-year work anniversary!\nThanks for three great years, Tom. 🙌"

    def test_a_first_anniversary(self):
        text = messages.celebration_text(anniv(FRI, ("U1", "Tom", 1)), FRI, MON_FRI)
        assert text == "🎉 Today is <@U1>'s first work anniversary! 🥳\nOne year already. Thanks for everything, Tom."

    def test_grouped_anniversaries_show_each_count(self):
        text = messages.celebration_text(anniv(FRI, ("U1", "A", 1), ("U2", "B", 5)), FRI, MON_FRI)
        assert "<@U1> (1 year) and <@U2> (5 years)" in text

    def test_no_name_still_reads_well(self):
        text = messages.celebration_text(bday(FRI, ("U1", "")), FRI, MON_FRI)
        assert text.endswith("Wishing you a lovely day. 💛")

    def test_no_gendered_pronouns(self):
        samples = [
            messages.celebration_text(c, FRI, MON_FRI)
            for c in (
                bday(FRI, ("U1", "A")),
                bday(FRI, ("U1", "A"), ("U2", "B")),
                bday(SUN, ("U1", "A")),
                anniv(FRI, ("U1", "A", 1)),
                anniv(FRI, ("U1", "A", 4)),
                anniv(FRI, ("U1", "A", 2), ("U2", "B", 3)),
            )
        ]
        for text in samples:
            words = set(text.lower().replace("!", " ").replace(".", " ").replace(",", " ").split())
            assert not words & {"he", "she", "his", "her", "him", "hers"}, text

    def test_names_are_escaped(self):
        assert messages.first_name("<!channel> Bob") == "&lt;!channel&gt;"

    def test_the_nudge_dm(self):
        text = messages.nudge_text("Priya", "C_CELEBRATE")
        assert text == (
            "👋 Hi Priya! Your team celebrates birthdays and work anniversaries in <#C_CELEBRATE>.\n\n"
            "Add yours so nobody misses it. For your birthday only the day and month are kept."
        )
        buttons = messages.nudge_blocks("Priya", "C_CELEBRATE")[1]["elements"]
        assert [b["text"]["text"] for b in buttons] == ["Add my dates", "Don't celebrate me"]
        assert all(b["action_id"].startswith("celebrations:") for b in buttons)


# ── The daily job ───────────────────────────────────────────────────────────


class Store:
    """The celebration_posts table, in memory, with the same primary key."""

    def __init__(self):
        self.posts: dict = {}
        self.released: list = []

    def claim(self, team, kind, day, posted_on, channel, user_ids):
        key = (team, kind, day)
        if key in self.posts:
            return False
        self.posts[key] = {"ts": None, "user_ids": list(user_ids), "posted_on": posted_on}
        return True

    def record(self, team, kind, day, ts):
        self.posts[(team, kind, day)]["ts"] = ts

    def release(self, team, kind, day):
        key = (team, kind, day)
        if key in self.posts and self.posts[key]["ts"] is None:
            del self.posts[key]
            self.released.append(key)


class Slack:
    def __init__(self, fail_posts=0):
        self.posts: list[dict] = []
        self.reactions: list[dict] = []
        self.dms: list[dict] = []
        self.fail_posts = fail_posts
        self.directory = []

    def chat_postMessage(self, **kw):
        if kw["channel"].startswith("U"):
            self.dms.append(kw)
            return {"ts": "dm"}
        if self.fail_posts:
            self.fail_posts -= 1
            raise RuntimeError("not_in_channel")
        self.posts.append(kw)
        return {"ts": f"{len(self.posts)}.000"}

    def reactions_add(self, **kw):
        self.reactions.append(kw)

    def users_info(self, user):
        return {"user": {"id": user, "profile": {"first_name": "Slack" + user}}}

    def users_list(self, **kw):
        return {"members": self.directory}


SETTINGS = {
    "team_id": "T1",
    "channel_id": "C_CELEBRATE",
    "timezone": "Europe/Berlin",
    "post_time": "09:00",
    "birthdays": True,
    "anniversaries": True,
}


@pytest.fixture
def world(monkeypatch):
    """A workspace with Celebrations on, a Mon to Fri week and an in-memory store."""
    store = Store()
    slack = Slack()
    state = {
        "rows": [],
        "settings": dict(SETTINGS),
        "calendar": Calendar(),
        "scopes": {"chat:write"},
        "active": True,
        "profiles": [],
        "claimed": [],
    }
    monkeypatch.setattr(core_modules, "is_active_for", lambda team, name: state["active"])
    monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team: dict(state["settings"]))
    monkeypatch.setattr("src.modules.celebrations.db.celebrants", lambda team: list(state["rows"]))
    monkeypatch.setattr("src.modules.celebrations.db.claim_post", store.claim)
    monkeypatch.setattr("src.modules.celebrations.db.record_post", store.record)
    monkeypatch.setattr("src.modules.celebrations.db.release_post", store.release)
    monkeypatch.setattr("src.modules.celebrations.db.purge_old_posts", lambda team: 0)
    monkeypatch.setattr(wc, "load_calendar", lambda team: state["calendar"])
    monkeypatch.setattr(jobs, "bot_client", lambda team: slack)
    monkeypatch.setattr(jobs, "DM_PAUSE_SECONDS", 0)
    monkeypatch.setattr("src.core.db.granted_scopes", lambda team: set(state["scopes"]))
    monkeypatch.setattr("src.core.db.list_member_profiles", lambda team, include_departed=False: state["profiles"])
    monkeypatch.setattr("src.core.db.get_active_members", lambda team: [])

    def claim(team, user_ids, cooldown_days=None):
        fresh = [u for u in user_ids if u not in state["claimed"]]
        state["claimed"].extend(fresh)
        return fresh

    monkeypatch.setattr("src.core.db.claim_profile_nudges", claim)
    return state, store, slack


def row(uid, name="", month=None, day=None, start=None):
    return {
        "user_id": uid,
        "display_name": name,
        "real_name": name,
        "birth_month": month,
        "birth_day": day,
        "start_date": start,
    }


# 08:00 UTC on Friday 25 September is 10:00 in Berlin.
FRIDAY_MORNING = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)


class TestDailyJob:
    def test_posts_each_kind_once_and_reacts_when_allowed(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25), row("U2", "Tom", start=date(2023, 9, 25))]
        state["scopes"] = {"chat:write", "reactions:write"}
        posted = jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert len(posted) == 2
        assert [p["channel"] for p in slack.posts] == ["C_CELEBRATE", "C_CELEBRATE"]
        assert slack.posts[0]["text"].startswith("🎂 Today is <@U1>'s birthday!")
        assert [r["name"] for r in slack.reactions] == ["tada", "tada"]

    def test_no_double_post_after_a_restart(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        # A restarted pod, a second pod, or the next hourly firing.
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        jobs.run_daily("T1", now=FRIDAY_MORNING.replace(hour=12))
        assert len(slack.posts) == 1

    def test_a_refused_post_is_released_for_the_next_firing(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        slack.fail_posts = 1
        assert jobs.run_daily("T1", now=FRIDAY_MORNING) == []
        assert store.released == [("T1", BIRTHDAY, FRI)]
        assert len(jobs.run_daily("T1", now=FRIDAY_MORNING.replace(hour=9))) == 1

    def test_the_reaction_is_skipped_without_the_scope(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        state["scopes"] = {"chat:write"}
        assert len(jobs.run_daily("T1", now=FRIDAY_MORNING)) == 1
        assert slack.reactions == []

    def test_a_failed_reaction_does_not_lose_the_post(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        state["scopes"] = {"reactions:write"}
        slack.reactions_add = MagicMock(side_effect=RuntimeError("missing_scope"))
        assert len(jobs.run_daily("T1", now=FRIDAY_MORNING)) == 1
        assert store.posts[("T1", BIRTHDAY, FRI)]["ts"] == "1.000"

    def test_friday_posts_the_weekend(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 26), row("U2", "Tom", 9, 27)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert [p["text"].split("\n")[0] for p in slack.posts] == [
            "🎂 Tomorrow is <@U1>'s birthday!",
            "🎂 On Sunday it's <@U2>'s birthday!",
        ]

    def test_nothing_runs_on_a_day_off(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 26)]
        assert jobs.run_daily("T1", now=datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)) == []
        assert slack.posts == []

    def test_the_celebrations_timezone_decides_the_day(self, world):
        """22:30 UTC on Thursday is already Friday in Berlin, still Thursday in Los Angeles."""
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        late_thursday = datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc)
        state["settings"]["timezone"] = "America/Los_Angeles"
        assert jobs.run_daily("T1", now=late_thursday) == []
        state["settings"]["timezone"] = "Europe/Berlin"
        assert len(jobs.run_daily("T1", now=late_thursday)) == 1

    def test_local_today_at_midnight(self):
        just_before = datetime(2026, 9, 24, 21, 59, tzinfo=timezone.utc)
        just_after = datetime(2026, 9, 24, 22, 0, tzinfo=timezone.utc)
        assert jobs.local_today("Europe/Berlin", just_before) == date(2026, 9, 24)
        assert jobs.local_today("Europe/Berlin", just_after) == FRI
        assert jobs.local_today("Not/AZone", just_after) is None

    def test_nothing_without_a_channel_or_timezone(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        state["settings"]["channel_id"] = None
        assert jobs.run_daily("T1", now=FRIDAY_MORNING) == []

    def test_nothing_when_the_module_is_off(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "Priya", 9, 25)]
        state["active"] = False
        assert jobs.run_daily("T1", now=FRIDAY_MORNING) == []

    def test_a_missing_name_is_looked_up_in_slack(self, world):
        state, store, slack = world
        state["rows"] = [row("U1", "", 9, 25)]
        jobs.run_daily("T1", now=FRIDAY_MORNING)
        assert "Wishing you a lovely day, SlackU1." in slack.posts[0]["text"]


class TestWhoIsCelebrated:
    """The filtering is SQL, so the statement is what is checked here; it was
    also run against Postgres 16 with every migration applied."""

    def test_opt_out_inactive_and_left_are_excluded(self, monkeypatch):
        seen = {}
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.execute.side_effect = lambda sql, params=(): seen.update(sql=" ".join(sql.split()))
        cur.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cur

        @contextmanager
        def fake_conn():
            yield conn

        monkeypatch.setattr("src.modules.celebrations.db.db_conn", fake_conn)
        _cdb().celebrants("T1")
        assert "AND p.celebrate" in seen["sql"]
        assert "AND p.left_at IS NULL" in seen["sql"]
        assert "AND COALESCE(m.active, TRUE)" in seen["sql"]

    def test_the_claim_is_one_atomic_insert(self, monkeypatch):
        seen = {}
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.execute.side_effect = lambda sql, params=(): seen.update(sql=" ".join(sql.split()))
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cur

        @contextmanager
        def fake_conn():
            yield conn

        monkeypatch.setattr("src.modules.celebrations.db.db_conn", fake_conn)
        assert _cdb().claim_post("T1", BIRTHDAY, FRI, FRI, "C1", ["U1"]) is False
        assert "ON CONFLICT (team_id, kind, celebration_date) DO NOTHING RETURNING 1" in seen["sql"]


# ── Planning the job ────────────────────────────────────────────────────────


class TestPlanJobs:
    def test_no_job_until_there_is_a_channel_and_a_timezone(self, monkeypatch):
        monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team: {**SETTINGS, "timezone": None})
        assert jobs.plan_jobs({"team_id": "T1"}) == []

    def test_the_job_fires_at_post_time_and_catches_up_hourly(self, monkeypatch):
        monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team: {**SETTINGS, "post_time": "08:30"})
        [job] = jobs.plan_jobs({"team_id": "T1"})
        assert job.key == "daily:0830:Europe/Berlin"
        assert job.args == ("T1",)
        assert job.func is jobs.run_daily
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["hour"] == "8-16"
        assert fields["minute"] == "30"
        assert str(job.trigger.timezone) == "Europe/Berlin"

    def test_changing_the_time_changes_the_job_id(self, monkeypatch):
        monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team: {**SETTINGS, "post_time": "10:00"})
        assert jobs.plan_jobs({"team_id": "T1"})[0].key == "daily:1000:Europe/Berlin"

    def test_reconciliation_keeps_a_planned_job(self, monkeypatch):
        """Reconciliation removes colon ids nobody planned; this one is planned."""
        from apscheduler.schedulers.background import BackgroundScheduler
        from src.core.scheduler import job_id, reconcile_jobs

        monkeypatch.setattr("src.modules.celebrations.db.get_settings", lambda team: dict(SETTINGS))
        [spec] = jobs.plan_jobs({"team_id": "T1"})
        scheduler = BackgroundScheduler()
        desired = {job_id("celebrations", "T1", spec.key): spec}
        reconcile_jobs(scheduler, desired)
        added, removed = reconcile_jobs(scheduler, desired)
        assert (added, removed) == ([], [])
        assert scheduler.get_job("celebrations:T1:daily:0900:Europe/Berlin") is not None


# ── Asking for dates ────────────────────────────────────────────────────────


class TestNudges:
    def test_the_first_ask_is_sent_once(self, world):
        state, store, slack = world
        slack.directory = [
            {"id": "U_NEW", "profile": {"first_name": "Priya"}},
            {"id": "U_HAS", "profile": {"first_name": "Tom"}},
            {"id": "U_BOT", "is_bot": True, "profile": {}},
        ]
        state["profiles"] = [{"user_id": "U_HAS", "birth_month": 3, "birth_day": 1, "celebrate": True}]
        assert jobs.send_first_nudges(slack, "T1", "C_CELEBRATE") == 1
        assert [d["channel"] for d in slack.dms] == ["U_NEW"]
        assert slack.dms[0]["text"].startswith("👋 Hi Priya!")
        state["profiles"].append({"user_id": "U_NEW", "nudged_at": datetime.now(timezone.utc), "celebrate": True})
        assert jobs.send_first_nudges(slack, "T1", "C_CELEBRATE") == 0
        assert len(slack.dms) == 1

    def test_people_who_opted_out_are_not_asked(self, world):
        state, store, slack = world
        slack.directory = [{"id": "U_OPT", "profile": {"first_name": "Opt"}}]
        state["profiles"] = [{"user_id": "U_OPT", "celebrate": False}]
        assert jobs.send_first_nudges(slack, "T1", "C_CELEBRATE") == 0

    def test_the_admin_ask_respects_30_days(self):
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        people = {"U_RECENT": "", "U_OLD": "", "U_NEVER": ""}

        def profiles(team, include_departed=False):
            return [
                {"user_id": "U_RECENT", "nudged_at": now - timedelta(days=5), "celebrate": True},
                {"user_id": "U_OLD", "nudged_at": now - timedelta(days=31), "celebrate": True},
            ]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.core.db.list_member_profiles", profiles)
            assert jobs.missing_dates("T1", people, cooldown_days=30) == ["U_NEVER", "U_OLD"]
            assert jobs.missing_dates("T1", people, cooldown_days=None) == ["U_NEVER"]

    def test_the_claim_sql_never_asks_twice(self, monkeypatch):
        seen = []
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.execute.side_effect = lambda sql, params=(): seen.append((" ".join(sql.split()), params))
        cur.fetchall.return_value = [("U1",)]
        conn = MagicMock()
        conn.cursor.return_value = cur

        @contextmanager
        def fake_conn():
            yield conn

        monkeypatch.setattr("src.core.db.db_conn", fake_conn)
        assert _core_db().claim_profile_nudges("T1", ["U1"]) == ["U1"]
        assert "WHERE member_profiles.nudged_at IS NULL AND member_profiles.celebrate" in seen[0][0]
        _core_db().claim_profile_nudges("T1", ["U1"], cooldown_days=30)
        assert "nudged_at < NOW() - make_interval(days => %s)" in seen[1][0]
        assert seen[1][1][-1] == 30
        assert _core_db().claim_profile_nudges("T1", []) == []


class TestSlackButtons:
    def _app(self):
        app = MagicMock()
        registered = {}
        app.action.side_effect = lambda action_id: lambda fn: registered.setdefault(action_id, fn)
        handlers.register_handlers(app)
        return registered

    def test_skip_me_turns_celebrating_off(self, monkeypatch):
        writes = []
        monkeypatch.setattr(
            "src.core.db.upsert_member_profile",
            lambda team, user, fields, updated_by: writes.append((user, fields)),
        )
        client = MagicMock()
        body = {
            "user": {"id": "U1"},
            "team": {"id": "T1"},
            "channel": {"id": "D1"},
            "message": {"ts": "1.0"},
        }
        self._app()[messages.SKIP_ACTION](ack=MagicMock(), body=body, client=client)
        assert writes == [("U1", {"celebrate": False})]
        assert client.chat_update.call_args.kwargs["text"] == messages.SKIPPED_TEXT

    def test_add_my_dates_opens_the_profile_modal(self, monkeypatch):
        import src.core.profile_slack as profile_slack

        opened = []
        monkeypatch.setattr(profile_slack, "open_profile_modal", lambda *args, **kw: opened.append(args))
        body = {"user": {"id": "U1"}, "team": {"id": "T1"}, "trigger_id": "trig"}
        self._app()[messages.ADD_DATES_ACTION](ack=MagicMock(), body=body, client=MagicMock())
        assert opened and opened[0][1:4] == ("trig", "T1", "U1")


class TestChannelJoin:
    @pytest.fixture
    def joined(self, world, monkeypatch):
        state, store, slack = world
        state["profile"] = None
        monkeypatch.setattr("src.core.db.get_member_profile", lambda team, user: state["profile"])
        return state, slack

    def event(self, channel="C_CELEBRATE"):
        return {"user": "U_JOIN", "channel": channel, "team": "T1"}

    def test_joining_the_channel_without_dates_asks_for_them(self, joined):
        state, slack = joined
        assert handlers.on_channel_join(self.event(), slack) is True
        assert [d["channel"] for d in slack.dms] == ["U_JOIN"]

    def test_not_for_another_channel(self, joined):
        state, slack = joined
        assert handlers.on_channel_join(self.event("C_OTHER"), slack) is False

    def test_not_for_someone_with_dates(self, joined):
        state, slack = joined
        state["profile"] = {"birth_month": 1, "birth_day": 2, "celebrate": True}
        assert handlers.on_channel_join(self.event(), slack) is False

    def test_not_when_the_module_is_off(self, joined):
        state, slack = joined
        state["active"] = False
        assert handlers.on_channel_join(self.event(), slack) is False

    def test_not_twice(self, joined):
        state, slack = joined
        handlers.on_channel_join(self.event(), slack)
        assert handlers.on_channel_join(self.event(), slack) is False
        assert len(slack.dms) == 1

    def test_not_for_a_bot(self, joined):
        state, slack = joined
        slack.users_info = lambda user: {"user": {"id": user, "is_bot": True}}
        assert handlers.on_channel_join(self.event(), slack) is False


class TestModuleSpec:
    def test_registered_off_by_default_and_delegable(self):
        from src.modules import REGISTRY

        spec = next(s for s in REGISTRY if s.name == "celebrations")
        assert spec.default_enabled is False
        assert spec.delegable is True
        assert spec.required_scopes == ()
        assert spec.plan_jobs is jobs.plan_jobs
        assert spec.on_channel_join is handlers.on_channel_join
        assert spec.help_lines

    def test_purge_removes_only_module_data(self, monkeypatch):
        seen = []
        cur = MagicMock()
        cur.__enter__.return_value = cur
        cur.execute.side_effect = lambda sql, params=(): seen.append(sql)
        conn = MagicMock()
        conn.cursor.return_value = cur

        @contextmanager
        def fake_conn():
            yield conn

        monkeypatch.setattr("src.modules.celebrations.db.db_conn", fake_conn)
        from src.modules.celebrations import purge

        purge("T1")
        assert seen == [
            "DELETE FROM celebration_posts WHERE team_id = %s",
            "DELETE FROM celebration_settings WHERE team_id = %s",
        ]
