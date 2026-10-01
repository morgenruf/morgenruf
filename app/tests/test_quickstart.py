"""Quick start: a standup from a channel and a time.

The bot cannot join a channel by itself (no channels:join scope), so most
teams pick a channel it is not in yet. That must save the standup waiting
for an invite and explain the one /invite step, never refuse. The invite
then switches it on and tells the creator once.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.modules.standup import quickstart


def _submit(bot_channels, picked="C1", tz="Europe/Berlin", may_manage=True):
    client = MagicMock()
    client.users_info.return_value = {"user": {"tz": tz}}
    ack = MagicMock()
    body = {"user": {"id": "U1", "team_id": "T1"}, "team": {"id": "T1"}}
    view = {
        "state": {
            "values": {
                "channel": {"channel": {"selected_conversation": picked}},
                "time": {"time": {"selected_time": "09:30"}},
            }
        }
    }
    with (
        patch.object(quickstart, "_bot_channel_ids", return_value=set(bot_channels)),
        patch.object(quickstart, "_may_manage", return_value=may_manage),
        patch("src.core.db.create_standup_schedule", return_value={"id": 7}) as create,
    ):
        quickstart.handle_submit(ack=ack, body=body, view=view, client=client)
    return ack, create, client


def test_bot_in_channel_creates_an_active_standup():
    ack, create, client = _submit(bot_channels=["C1"])
    ack.assert_called_once_with()
    kwargs = create.call_args.kwargs
    assert create.call_args.args == ("T1",)
    assert kwargs["active"] is True
    assert kwargs["awaiting_invite_by"] is None
    assert kwargs["sync_with_channel"] is True
    assert kwargs["schedule_tz"] == "Europe/Berlin"
    assert kwargs["schedule_time"] == "09:30"
    assert kwargs["schedule_days"] == "mon,tue,wed,thu,fri"
    assert kwargs["participants"] == []
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "<#C1>" in text and "/invite" not in text


def test_bot_not_in_channel_saves_it_waiting_and_explains_the_invite():
    ack, create, client = _submit(bot_channels=[])
    ack.assert_called_once_with()
    kwargs = create.call_args.kwargs
    assert kwargs["active"] is False
    assert kwargs["awaiting_invite_by"] == "U1"
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "/invite @Morgenruf" in text and "<#C1>" in text


def test_a_private_channel_the_bot_cannot_see_takes_the_same_waiting_path():
    """users.conversations lists only channels the bot is in, so a private
    channel picked from the user's own list looks exactly like any other
    channel the bot has not been invited to."""
    ack, create, client = _submit(bot_channels=["C_OTHER"], picked="G_PRIVATE")
    assert create.call_args.kwargs["awaiting_invite_by"] == "U1"
    assert "<#G_PRIVATE>" in client.chat_postMessage.call_args.kwargs["text"]


def test_an_unusable_slack_timezone_falls_back_to_utc():
    _, create, _ = _submit(bot_channels=["C1"], tz="Mars/Olympus")
    assert create.call_args.kwargs["schedule_tz"] == "UTC"


def test_missing_channel_is_a_field_error_not_a_crash():
    ack, create, _ = _submit(bot_channels=[], picked=None)
    ack.assert_called_once()
    assert ack.call_args.kwargs["response_action"] == "errors"
    assert "channel" in ack.call_args.kwargs["errors"]
    create.assert_not_called()


def test_someone_who_may_not_manage_standups_gets_a_field_error():
    ack, create, _ = _submit(bot_channels=["C1"], may_manage=False)
    assert ack.call_args.kwargs["response_action"] == "errors"
    create.assert_not_called()


def test_opening_checks_the_role_first():
    client = MagicMock()
    ack = MagicMock()
    body = {"user": {"id": "U1", "team_id": "T1"}, "trigger_id": "tr"}
    with patch.object(quickstart, "_may_manage", return_value=False):
        quickstart.handle_open(ack=ack, body=body, client=client)
    ack.assert_called_once_with()
    client.views_open.assert_not_called()

    client.users_info.return_value = {"user": {"tz": "Asia/Kolkata"}}
    with patch.object(quickstart, "_may_manage", return_value=True):
        quickstart.handle_open(ack=ack, body=body, client=client)
    view = client.views_open.call_args.kwargs["view"]
    assert view["callback_id"] == quickstart.CALLBACK_ID
    assert "Asia/Kolkata" in str(view["blocks"])
    picker = view["blocks"][0]["element"]
    assert picker["type"] == "conversations_select"
    assert picker["filter"]["include"] == ["public", "private"]


def test_invite_switches_waiting_standups_on_and_tells_the_creator_once():
    client = MagicMock()
    rows = [{"id": 7, "awaiting_invite_by": "U1", "schedule_time": "09:30"}]
    with (
        patch("src.core.db.waiting_standups", return_value=rows),
        patch("src.core.db.activate_waiting_standup", side_effect=[True, False]) as activate,
    ):
        assert quickstart.activate_waiting(client, "T1", "C1") == 1
        assert quickstart.activate_waiting(client, "T1", "C1") == 0
    assert activate.call_count == 2
    assert client.chat_postMessage.call_count == 1
    assert client.chat_postMessage.call_args.kwargs["channel"] == "U1"


def test_invite_with_nothing_waiting_does_nothing():
    client = MagicMock()
    with patch("src.core.db.waiting_standups", return_value=[]):
        assert quickstart.activate_waiting(client, "T1", "C9") == 0
    client.chat_postMessage.assert_not_called()


def test_button_block_has_its_own_block_id():
    block = quickstart.button_block()
    assert block["type"] == "actions" and block["block_id"] == "quickstart"
    assert block["elements"][0]["action_id"] == quickstart.OPEN_ACTION


# ── The invite reaches the quick start through the channel join hook ─────────


def _join(user, bot_user_id="UBOT"):
    from src.modules.standup import handlers

    client = MagicMock()
    client.users_info.return_value = {"user": {"id": user, "is_bot": user == "UBOT", "profile": {}}}
    fake_db = MagicMock()
    fake_db.get_installation.return_value = {"bot_user_id": bot_user_id}
    fake_db.get_standup_schedule_for_channel.return_value = None
    with (
        patch("src.core.db.get_installation", fake_db.get_installation),
        patch("src.core.db.get_standup_schedule_for_channel", fake_db.get_standup_schedule_for_channel),
        patch("src.core.db.upsert_member"),
        patch.object(quickstart, "activate_waiting", return_value=1) as activate,
    ):
        handlers.on_channel_join({"user": user, "team": "T1", "channel": "C1"}, client)
    return activate, client


def test_the_bot_joining_switches_on_what_waits_for_it():
    activate, client = _join("UBOT")
    activate.assert_called_once_with(client, "T1", "C1")


def test_a_person_joining_does_not():
    activate, _ = _join("U2")
    activate.assert_not_called()


# ── Database ────────────────────────────────────────────────────────────────


def test_activation_only_succeeds_while_still_waiting(fake_cursor_db):
    from src.core import db

    fake_cursor_db._fetchone = [(1,), None]
    assert db.activate_waiting_standup(7) is True
    assert db.activate_waiting_standup(7) is False
    sql, params = fake_cursor_db.calls[0]
    assert "awaiting_invite_by IS NOT NULL" in sql.split("WHERE", 1)[1]
    assert "updated_at = NOW()" in sql and "active = TRUE" in sql
    assert params == (7,)


def test_waiting_standups_reads_only_waiting_rows_for_the_channel(fake_cursor_db):
    from src.core import db

    db.waiting_standups("T1", "C1")
    sql, params = fake_cursor_db.calls[0]
    assert "awaiting_invite_by IS NOT NULL" in sql
    assert params == ("T1", "C1")


def test_create_accepts_awaiting_invite_by(fake_cursor_db):
    from src.core import db

    fake_cursor_db._fetchone = [{"id": 1}]
    db.create_standup_schedule("T1", channel_id="C1", awaiting_invite_by="U1", active=False)
    sql, params = fake_cursor_db.calls[0]
    assert "awaiting_invite_by" in sql
    assert "U1" in params
