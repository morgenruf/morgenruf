"""Every step between an installed workspace and a live coffee chat job.

reconcile_jobs is covered on its own; what was not is the walk that feeds it.
Staging showed why it matters: its programme was enabled and its module active,
and no round job existed, because every installation row there is deactivated.
That turned out to be correct (a dead token cannot deliver a round), but
nothing proved it either way.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.scheduler import sync_module_jobs


class FakeScheduler:
    def __init__(self, existing=()):
        self.jobs = {i: MagicMock(id=i) for i in existing}
        self.added = []
        self.removed = []

    def get_jobs(self):
        return list(self.jobs.values())

    def add_job(self, func, trigger, args=(), id=None, replace_existing=False):
        self.added.append(id)
        self.jobs[id] = MagicMock(id=id)

    def remove_job(self, jid):
        self.removed.append(jid)
        self.jobs.pop(jid, None)


def module(name, jobs):
    spec = MagicMock()
    spec.name = name
    spec.plan_jobs = MagicMock(return_value=jobs)
    return spec


def job(key):
    from src.core.scheduler import JobSpec

    return JobSpec(key=key, trigger=MagicMock(), func=lambda: None)


@pytest.fixture()
def wiring(monkeypatch):
    """Patch the four things sync_module_jobs reaches for, and hand them back."""
    import src.core.db as db
    import src.core.modules as core_modules
    import src.modules as registry_mod

    state = {
        "installations": [{"team_id": "T1", "bot_token": "xoxb-1"}],
        "active": [module("connect", [job("round:7")])],
    }
    monkeypatch.setattr(db, "get_all_installations", lambda: list(state["installations"]))
    monkeypatch.setattr(db, "granted_scopes", lambda t: ["chat:write"])
    monkeypatch.setattr(db, "module_settings", lambda t: {})
    monkeypatch.setattr(core_modules, "deploy_allowlist", lambda: None)
    monkeypatch.setattr(core_modules, "active_modules", lambda *a, **k: state["active"])
    monkeypatch.setattr(registry_mod, "REGISTRY", tuple(state["active"]), raising=False)
    return state


def test_an_installed_workspace_gets_its_modules_jobs(wiring):
    s = FakeScheduler()
    added, removed = sync_module_jobs(s)
    assert added == ["connect:T1:round:7"]
    assert s.added == ["connect:T1:round:7"]


def test_a_deactivated_installation_gets_nothing(wiring):
    """get_all_installations hides them, so the walk never reaches the module.

    A token Slack has invalidated cannot deliver a round, so the job would only
    fire and fail.
    """
    wiring["installations"] = []
    s = FakeScheduler()
    added, removed = sync_module_jobs(s)
    assert added == [] and s.added == []


def test_a_job_disappears_when_the_module_is_switched_off(wiring):
    s = FakeScheduler(existing=["connect:T1:round:7"])
    wiring["active"] = []
    added, removed = sync_module_jobs(s)
    assert removed == ["connect:T1:round:7"]
    assert s.removed == ["connect:T1:round:7"]


def test_one_module_failing_does_not_cost_the_others_their_jobs(wiring):
    broken = module("broken", [])
    broken.plan_jobs.side_effect = RuntimeError("bad programme row")
    wiring["active"] = [broken, module("connect", [job("round:7")])]
    s = FakeScheduler()
    added, _ = sync_module_jobs(s)
    assert added == ["connect:T1:round:7"]


def test_a_module_with_no_jobs_to_plan_is_skipped(wiring):
    spec = module("insights", [])
    spec.plan_jobs = None
    wiring["active"] = [spec]
    s = FakeScheduler()
    assert sync_module_jobs(s) == ([], [])


def test_one_workspace_failing_does_not_stop_the_next(wiring, monkeypatch):
    import src.core.db as db

    wiring["installations"] = [{"team_id": "T0", "bot_token": "x"}, {"team_id": "T1", "bot_token": "y"}]
    monkeypatch.setattr(
        db, "granted_scopes", lambda t: (_ for _ in ()).throw(RuntimeError("pool")) if t == "T0" else ["chat:write"]
    )
    s = FakeScheduler()
    added, _ = sync_module_jobs(s)
    assert added == ["connect:T1:round:7"]


def test_a_row_without_a_team_id_is_ignored(wiring):
    wiring["installations"] = [{"bot_token": "x"}]
    s = FakeScheduler()
    assert sync_module_jobs(s) == ([], [])
