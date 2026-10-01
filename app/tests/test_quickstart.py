"""Quick start: a standup from a channel and a time.

The bot cannot join a channel by itself (no channels:join scope), so most
teams pick a channel it is not in yet. That must save the standup waiting
for an invite and explain the one /invite step, never refuse. The invite
then switches it on and tells the creator once.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.core import standup_invites
from src.modules.standup import quickstart


def _submit(
    bot_channels,
    picked="C1",
    tz="Europe/Berlin",
    may_manage=True,
    humans=("U1", "U2"),
    existing=(),
    membership_error=None,
):
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
    bot_ids = MagicMock(return_value=set(bot_channels), side_effect=membership_error)
    with (
        patch.object(quickstart, "_bot_channel_ids", bot_ids),
        patch.object(quickstart, "_channel_humans", return_value=list(humans)),
        patch.object(quickstart, "_may_manage", return_value=may_manage),
        patch("src.core.db.get_standup_schedules", return_value=[{"id": 1, "channel_id": c} for c in existing]),
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
    assert kwargs["participants"] == ["U1", "U2"]
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "<#C1>" in text and "/invite" not in text
    assert "09:30 Europe/Berlin" in text


def test_bot_not_in_channel_saves_it_waiting_and_explains_the_invite():
    ack, create, client = _submit(bot_channels=[])
    ack.assert_called_once_with()
    kwargs = create.call_args.kwargs
    assert kwargs["active"] is False
    assert kwargs["awaiting_invite_by"] == "U1"
    assert kwargs["participants"] == []
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "/invite @Morgenruf" in text and "<#C1>" in text
    # Typing the command and pressing Enter can open Slack's command menu instead
    # of running it, so the DM also names the menu path that always works.
    assert "Add agents and apps" in text
    assert "09:30 Europe/Berlin" in text


def test_a_failed_membership_check_saves_nothing_and_says_so():
    """Saving it as waiting would leave it off for ever: a bot that is already
    in the channel gets no member_joined_channel to switch it on."""
    ack, create, client = _submit(bot_channels=["C1"], membership_error=RuntimeError("ratelimited"))
    ack.assert_called_once_with()
    create.assert_not_called()
    assert "Couldn't check the channel, please try again" in client.chat_postMessage.call_args.kwargs["text"]


def test_a_second_press_for_the_same_channel_is_a_field_error():
    ack, create, _ = _submit(bot_channels=["C1"], existing=["C1"])
    assert ack.call_args.kwargs["response_action"] == "errors"
    assert "already has a standup" in ack.call_args.kwargs["errors"]["channel"]
    create.assert_not_called()


def test_another_channel_with_a_standup_does_not_block_this_one():
    ack, create, _ = _submit(bot_channels=["C1"], existing=["C9"])
    ack.assert_called_once_with()
    create.assert_called_once()


def test_a_conversation_that_is_not_a_channel_is_a_field_error():
    for picked in ("D123", "U123", "X1"):
        ack, create, _ = _submit(bot_channels=[], picked=picked)
        assert ack.call_args.kwargs["response_action"] == "errors", picked
        assert "channel" in ack.call_args.kwargs["errors"]
        create.assert_not_called()


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
    assert "default_to_current_conversation" not in picker


WAITING = [{"id": 7, "awaiting_invite_by": "U1", "schedule_time": "09:30", "schedule_tz": "Europe/Berlin"}]


def test_invite_switches_waiting_standups_on_and_tells_the_creator_once():
    client = MagicMock()
    with (
        patch("src.core.db.waiting_standups", return_value=WAITING),
        patch("src.core.db.activate_waiting_standup", side_effect=[True, False]) as activate,
        patch("src.core.db.update_standup_schedule"),
        patch.object(standup_invites, "channel_humans", return_value=["U1"]),
    ):
        assert quickstart.activate_waiting(client, "T1", "C1") == 1
        assert quickstart.activate_waiting(client, "T1", "C1") == 0
    assert activate.call_count == 2
    assert client.chat_postMessage.call_count == 1
    kwargs = client.chat_postMessage.call_args.kwargs
    assert kwargs["channel"] == "U1"
    assert "09:30 Europe/Berlin" in kwargs["text"]


def test_activation_seeds_participants_from_the_channel():
    client = MagicMock()
    with (
        patch("src.core.db.waiting_standups", return_value=WAITING),
        patch("src.core.db.activate_waiting_standup", return_value=True),
        patch("src.core.db.update_standup_schedule") as update,
        patch.object(standup_invites, "channel_humans", return_value=["U1", "U2"]),
    ):
        quickstart.activate_waiting(client, "T1", "C1")
    update.assert_called_once_with("T1", 7, participants=["U1", "U2"])


def test_a_failed_seed_still_switches_it_on():
    """The scheduler refuses to run a synced standup with nobody to ask, so a
    seed that fails here cannot fall back to the whole workspace."""
    client = MagicMock()
    with (
        patch("src.core.db.waiting_standups", return_value=WAITING),
        patch("src.core.db.activate_waiting_standup", return_value=True),
        patch("src.core.db.update_standup_schedule") as update,
        patch.object(standup_invites, "channel_humans", side_effect=RuntimeError("ratelimited")),
    ):
        assert quickstart.activate_waiting(client, "T1", "C1") == 1
    update.assert_not_called()
    client.chat_postMessage.assert_called_once()


def test_invite_with_nothing_waiting_does_nothing():
    client = MagicMock()
    with patch("src.core.db.waiting_standups", return_value=[]):
        assert quickstart.activate_waiting(client, "T1", "C9") == 0
    client.chat_postMessage.assert_not_called()


# ── The hourly safety net ───────────────────────────────────────────────────


def test_the_sweep_switches_on_standups_whose_channel_the_bot_is_now_in():
    """No member_joined_channel arrives for a bot that was already in the
    channel, or for an event Slack dropped. The hourly sweep catches both."""
    client = MagicMock()
    teams = [{"team_id": "T1", "bot_token": "xoxb-1", "channel_ids": ["C1", "C2"]}]
    with (
        patch("src.core.db.teams_with_waiting_standups", return_value=teams),
        patch.object(standup_invites, "_bot_token", lambda team_id, stored: stored),
        patch.object(standup_invites, "WebClient", return_value=client),
        patch.object(standup_invites, "bot_channel_ids", return_value={"C1", "C9"}) as member_of,
        patch.object(standup_invites, "activate_waiting", return_value=1) as activate,
    ):
        assert standup_invites.sweep_waiting_standups() == 1
    member_of.assert_called_once_with(client)
    activate.assert_called_once_with(client, "T1", "C1")


def test_one_failing_team_does_not_stop_the_sweep():
    teams = [
        {"team_id": "T1", "bot_token": "xoxb-1", "channel_ids": ["C1"]},
        {"team_id": "T2", "bot_token": "xoxb-2", "channel_ids": ["C2"]},
    ]
    with (
        patch("src.core.db.teams_with_waiting_standups", return_value=teams),
        patch.object(standup_invites, "_bot_token", lambda team_id, stored: stored),
        patch.object(standup_invites, "WebClient", return_value=MagicMock()),
        patch.object(standup_invites, "bot_channel_ids", side_effect=[RuntimeError("account_inactive"), {"C2"}]),
        patch.object(standup_invites, "activate_waiting", return_value=1) as activate,
    ):
        assert standup_invites.sweep_waiting_standups() == 1
    assert activate.call_args.args[1:] == ("T2", "C2")


def test_bot_channel_ids_raises_on_a_slack_error_instead_of_returning_a_partial_list():
    client = MagicMock()
    client.users_conversations.side_effect = [
        {"channels": [{"id": "C1"}], "response_metadata": {"next_cursor": "n"}},
        RuntimeError("ratelimited"),
    ]
    try:
        standup_invites.bot_channel_ids(client)
    except RuntimeError:
        pass
    else:
        raise AssertionError("a partial list would save a joined standup as waiting")


def test_bot_channel_ids_follows_pages():
    client = MagicMock()
    client.users_conversations.side_effect = [
        {"channels": [{"id": "C1"}], "response_metadata": {"next_cursor": "n"}},
        {"channels": [{"id": "G2"}], "response_metadata": {}},
    ]
    assert standup_invites.bot_channel_ids(client) == {"C1", "G2"}


def test_channel_humans_drops_bots():
    client = MagicMock()
    client.conversations_members.return_value = {"members": ["U1", "UBOT"], "response_metadata": {}}
    with patch.object(standup_invites, "filter_human_ids", return_value={"U1"}):
        assert standup_invites.channel_humans(client, "C1") == ["U1"]


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


def test_teams_with_waiting_standups_reads_live_installs_only(fake_cursor_db):
    from src.core import db

    db.teams_with_waiting_standups()
    sql = fake_cursor_db.calls[0][0]
    assert "awaiting_invite_by IS NOT NULL" in sql and "i.active" in sql


def test_waiting_standups_carries_the_timezone(fake_cursor_db):
    from src.core import db

    db.waiting_standups("T1", "C1")
    assert "schedule_tz" in fake_cursor_db.calls[0][0]


def test_any_update_clears_the_waiting_flag(fake_cursor_db):
    """Editing or resuming a waiting standup by hand takes it over: the invite
    must not switch it on later, and Home must stop saying it waits."""
    from src.core import db

    fake_cursor_db._fetchone = [{"id": 7}]
    db.update_standup_schedule("T1", 7, active=True)
    assert "awaiting_invite_by = NULL" in fake_cursor_db.calls[0][0]


# ── App Home ────────────────────────────────────────────────────────────────


def _card(**kw):
    base = {
        "standup_id": "7",
        "standup_name": "Daily standup",
        "channel_id": "C1",
        "active": False,
        "awaiting_invite_by": "U1",
    }
    return {**base, **kw}


def test_home_says_a_waiting_standup_waits_for_the_invite():
    import src.modules.standup.blocks as blocks

    text = str(blocks.app_home_view(standups=[_card()], user_id="U1")["blocks"])
    assert "Waiting for `/invite @Morgenruf` in <#C1>" in text
    assert "Paused" not in text


def test_home_still_says_paused_for_a_paused_standup():
    import src.modules.standup.blocks as blocks

    text = str(blocks.app_home_view(standups=[_card(awaiting_invite_by=None)], user_id="U1")["blocks"])
    assert "Paused" in text and "Waiting for" not in text


def test_the_settings_view_says_it_waits_too():
    import src.modules.standup.blocks as blocks

    view = blocks.app_home_configure_view(standups=[_card()], user_id="U1")
    text = str(view["blocks"])
    assert "Waiting for `/invite @Morgenruf` in <#C1>" in text
    assert "*Paused*" not in text
