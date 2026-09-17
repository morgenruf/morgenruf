"""The schedule's Report Channel field has to actually move the report.

It was saved, read back by the API and rendered in the form, and then
ignored: _post_scheduled_report always posted to the standup channel. The
field's own placeholder says "Same as standup channel", so an empty value
means the standup channel and anything else means somewhere different.
"""

from unittest.mock import MagicMock, patch

import src.core.scheduler as sched_mod

from tests.support import patch_modules


def _standups():
    return [{"user_id": "U1", "yesterday": "a", "today": "b", "blockers": "", "has_blockers": False}]


def _db(report_channel=""):
    db = MagicMock()
    db.get_today_standups.return_value = _standups()
    db.get_standup_schedule.return_value = {
        "id": 1,
        "name": "Daily standup",
        "participants": ["U1"],
        "questions": [],
        "post_summary": True,
        "group_by": "member",
        "report_channel": report_channel,
    }
    db.get_workspace_config.return_value = {"questions": [], "ai_summary_enabled": False}
    db.get_daily_thread_ts.return_value = None
    db.get_installation.return_value = {"team_name": "Acme", "bot_token": "xoxb-test"}
    return db


def _run(db):
    client = MagicMock()
    client.token = "xoxb-test"
    client.chat_postMessage.return_value = {"ts": "111.222"}
    with (
        patch_modules({"src.core.db": db}),
        patch.object(sched_mod, "WebClient", return_value=client),
        patch.object(sched_mod, "_fresh_bot_token", return_value="xoxb-test"),
        patch.object(sched_mod, "_call_with_auth_retry", return_value=None),
    ):
        sched_mod._post_scheduled_report("T1", "xoxb-test", "C_STANDUP", 1)
    return client


class TestReportChannel:
    def test_empty_means_the_standup_channel(self):
        client = _run(_db(""))
        assert client.chat_postMessage.call_args.kwargs["channel"] == "C_STANDUP"

    def test_a_different_channel_is_used(self):
        client = _run(_db("C_MANAGERS"))
        assert client.chat_postMessage.call_args.kwargs["channel"] == "C_MANAGERS"

    def test_a_different_channel_is_not_threaded(self):
        # A thread_ts belongs to the channel it was created in. Carrying the
        # standup channel's parent into another channel makes Slack reject the
        # post, which would turn a working report into no report at all.
        db = _db("C_MANAGERS")
        db.get_daily_thread_ts.return_value = "999.888"
        client = _run(db)
        assert "thread_ts" not in client.chat_postMessage.call_args.kwargs

    def test_the_standup_channel_still_threads(self):
        db = _db("")
        db.get_daily_thread_ts.return_value = "999.888"
        client = _run(db)
        assert client.chat_postMessage.call_args.kwargs["thread_ts"] == "999.888"
