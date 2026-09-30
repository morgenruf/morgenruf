"""Schedule edits from the App Home apply within seconds.

The App Home pause, enable and delete handlers called remove_job and
register_schedule_job on get_scheduler(). The scheduler runs in the gunicorn
master; in the forked web worker those calls act on a copy that never runs,
so the change only applied at the next two minute sync. The handlers now only
write the database, and a cheap poll in the scheduler notices the change.
"""

import inspect
from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod
import src.modules.standup.handlers as handlers

from tests.support import patch_modules


class TestChangePoll:
    def setup_method(self):
        sched_mod._schedule_marker = None

    def teardown_method(self):
        sched_mod._schedule_marker = None

    def _poll(self, marker):
        db = MagicMock()
        db.schedules_change_marker.return_value = marker
        with patch_modules({"src.core.db": db}), patch.object(sched_mod, "_sync_jobs_from_db") as sync:
            sched_mod._poll_schedule_changes()
        return sync

    def test_first_look_syncs(self):
        assert self._poll((3, "t1")).call_count == 1

    def test_unchanged_marker_does_nothing(self):
        self._poll((3, "t1"))
        assert self._poll((3, "t1")).call_count == 0

    def test_an_edit_or_a_delete_syncs(self):
        self._poll((3, "t1"))
        assert self._poll((3, "t2")).call_count == 1  # edited, paused or enabled
        assert self._poll((2, "t2")).call_count == 1  # deleted

    def test_a_failed_lookup_does_not_sync_or_raise(self):
        db = MagicMock()
        db.schedules_change_marker.side_effect = Exception("db down")
        with patch_modules({"src.core.db": db}), patch.object(sched_mod, "_sync_jobs_from_db") as sync:
            sched_mod._poll_schedule_changes()
        sync.assert_not_called()

    def test_the_poll_is_registered_with_the_scheduler(self):
        scheduler = sched_mod.build_scheduler([])
        try:
            job = scheduler.get_job("schedule_change_poll")
            assert job is not None
            assert job.trigger.interval.total_seconds() == sched_mod._CHANGE_POLL_SECONDS
        finally:
            sched_mod._scheduler = None


def test_app_home_handlers_do_not_touch_the_workers_dead_scheduler():
    source = inspect.getsource(handlers)
    assert "get_scheduler" not in source
    assert "register_schedule_job(" not in source
    assert ".remove_job(" not in source
