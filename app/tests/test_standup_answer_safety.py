"""Standup answers stay text, and only standup admins change standups from App Home.

Answers are posted to the channel under the bot's name. Typing `<!channel>`
in the form pinged the whole channel, and `<https://evil|PROJ-12>` showed a
disguised link. Separately, App Home let any member create, edit, pause or
delete standups, while the dashboard asked for the standup admin grant.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from tests.support import patch_modules

sys.modules.setdefault("slack_bolt", MagicMock())
sys.modules.setdefault("requests", MagicMock())
if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]
import pytz as _real_pytz  # noqa: E402

_prior_session_store = sys.modules.get("src.core.session_store")
_ss_mock = MagicMock()
_ss_mock.get_session.return_value = None
_ss_mock.has_session.return_value = False
sys.modules["src.core.session_store"] = _ss_mock

import src.core.schedule_validation as schedule_validation  # noqa: E402
import src.modules.standup.blocks as blocks  # noqa: E402
import src.modules.standup.handlers as handlers  # noqa: E402

if _prior_session_store is not None:
    sys.modules["src.core.session_store"] = _prior_session_store
else:
    sys.modules.pop("src.core.session_store", None)


class TestEscaping:
    def test_plain_text_is_escaped(self):
        assert blocks.escape_mrkdwn("<!channel> & <https://evil|PROJ-12>") == (
            "&lt;!channel&gt; &amp; &lt;https://evil|PROJ-12&gt;"
        )

    def test_rich_text_typed_brackets_stay_text(self):
        rt = {"elements": [{"type": "rich_text_section", "elements": [{"type": "text", "text": "<!here> ship it"}]}]}
        assert blocks.rich_text_to_mrkdwn(rt) == "&lt;!here&gt; ship it"

    def test_rich_text_mentions_and_links_still_work(self):
        rt = {
            "elements": [
                {
                    "type": "rich_text_section",
                    "elements": [
                        {"type": "user", "user_id": "U123"},
                        {"type": "text", "text": " fixed "},
                        {"type": "link", "url": "https://jira.example.com/PROJ-1", "text": "PROJ-1"},
                    ],
                }
            ]
        }
        assert blocks.rich_text_to_mrkdwn(rt) == "<@U123> fixed <https://jira.example.com/PROJ-1|PROJ-1>"

    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("<!channel> look", "@channel look"),
            ("<!here|here> now", "@here now"),
            ("<!everyone>", "@everyone"),
            ("ping <!subteam^S123|@eng>", "ping @eng"),
            ("<@U1> and <https://x.example.com|x>", "<@U1> and <https://x.example.com|x>"),
        ],
    )
    def test_dm_answers_lose_broadcasts_only(self, given, expected):
        assert handlers.answer_value(given) == expected


class TestEditRoundTrip:
    @pytest.mark.parametrize(
        "stored",
        [
            "&lt;!channel&gt; &amp; more",
            "<@U123> fixed <https://jira.example.com/PROJ-1|PROJ-1> in <#C42>",
            "plain words",
            "",
        ],
    )
    def test_saving_an_unchanged_edit_stores_the_same_text(self, stored):
        assert blocks.rich_text_to_mrkdwn(blocks.mrkdwn_to_rich_text(stored)) == stored

    def test_editor_shows_what_the_member_typed(self):
        rt = blocks.mrkdwn_to_rich_text("a &lt; b &amp;&amp; c")
        assert rt["elements"][0]["elements"] == [{"type": "text", "text": "a < b && c"}]


def _handlers():
    captured: dict = {}

    def register(kind):
        def deco_factory(name):
            def decorator(fn):
                captured[(kind, name if isinstance(name, str) else name.pattern)] = fn
                return fn

            return decorator

        return deco_factory

    app = MagicMock()
    app.view.side_effect = register("view")
    app.action.side_effect = register("action")
    handlers.register_handlers(app)
    return captured


def _modal_body():
    return {
        "user": {"id": "U_MEMBER"},
        "team": {"id": "T1"},
        "view": {
            "private_metadata": "",
            "state": {
                "values": {
                    "standup_channel": {"standup_channel": {"selected_channel": "C1"}},
                    "questions": {"questions": {"value": "What did you do?"}},
                    "standup_time": {"standup_time": {"selected_option": {"value": "09:30"}}},
                    "timezone": {"timezone": {"selected_option": {"value": "UTC"}}},
                    "reminder": {"reminder": {"selected_option": {"value": "0"}}},
                    "members": {"members": {"selected_users": ["U2"]}},
                    "days": {"days": {"selected_options": [{"value": "mon"}]}},
                    "standup_name": {"standup_name": {"value": "Daily"}},
                }
            },
        },
    }


class TestStandupAdminGuard:
    def setup_method(self):
        self.handlers = _handlers()
        self.db = MagicMock()
        self.client = MagicMock()

    def _as(self, allowed: bool):
        self.db.can_administer.return_value = allowed
        return (
            patch_modules({"src.core.db": self.db}),
            patch.object(schedule_validation, "pytz", _real_pytz),
        )

    def test_member_cannot_create_from_the_modal(self):
        ack = MagicMock()
        a, b = self._as(False)
        with a, b:
            self.handlers[("view", "create_standup_modal")](ack, _modal_body(), self.client)
        self.db.create_standup_schedule.assert_not_called()
        assert ack.call_args.kwargs["response_action"] == "errors"
        self.db.can_administer.assert_called_with("T1", "U_MEMBER", "standup")

    def test_standup_admin_can_create(self):
        self.db.create_standup_schedule.return_value = None
        a, b = self._as(True)
        with a, b:
            self.handlers[("view", "create_standup_modal")](MagicMock(), _modal_body(), self.client)
        self.db.create_standup_schedule.assert_called_once()

    @pytest.mark.parametrize(
        ("action", "actions"),
        [
            ("open_create_standup", [{"value": "create"}]),
            ("edit_standup", [{"value": "7"}]),
            ("delete_standup", [{"value": "7"}]),
            ("standup_overflow", [{"selected_option": {"value": "delete_7"}}]),
        ],
    )
    def test_member_cannot_manage_from_app_home(self, action, actions):
        body = {
            "user": {"id": "U_MEMBER", "team_id": "T1"},
            "team": {"id": "T1"},
            "trigger_id": "x",
            "actions": actions,
        }
        a, b = self._as(False)
        with a, b:
            self.handlers[("action", action)](MagicMock(), body, self.client)
        self.client.views_open.assert_not_called()
        self.db.delete_standup_schedule.assert_not_called()
        self.db.update_standup_schedule.assert_not_called()
        assert handlers._NOT_A_STANDUP_ADMIN in self.client.chat_postMessage.call_args.kwargs["text"]

    def test_a_failed_role_lookup_refuses(self):
        self.db.can_administer.side_effect = RuntimeError("db down")
        with patch_modules({"src.core.db": self.db}):
            assert handlers.may_manage_standups("T1", "U1") is False


class TestReportedAtIsLocal:
    """App Home said "Reported at 12:25 AM" for an 8:25 PM New York answer."""

    def test_utc_timestamp_shown_in_the_readers_zone(self):
        from datetime import datetime, timezone

        moment = datetime(2026, 9, 30, 0, 25, tzinfo=timezone.utc)
        assert handlers._local_clock(moment, "America/New_York") == "8:25 PM"

    def test_legacy_alias_and_bad_zone(self):
        from datetime import datetime, timezone

        moment = datetime(2026, 9, 30, 0, 25, tzinfo=timezone.utc)
        assert handlers._local_clock(moment, "Asia/Calcutta") == "5:55 AM"
        assert handlers._local_clock(moment, "Not/AZone") == "12:25 AM"
        assert handlers._local_clock(moment.replace(tzinfo=None), None) == "12:25 AM"
