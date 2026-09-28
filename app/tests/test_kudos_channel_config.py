"""The kudos channel is a kudos setting, saved and read through the kudos config API.

Before this, the card went to workspace_config.channel_id, which nothing in
the dashboard or the API sets, so no workspace could choose where kudos were
shared.
"""

from __future__ import annotations

import pathlib
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from tests.browser_fixtures import create_test_app

MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "src" / "modules" / "kudos" / "migrations"


@pytest.fixture
def browser(monkeypatch):
    app = create_test_app(monkeypatch)
    return app, app.test_client()


def _as(client, role):
    token = client.post(f"/__test__/session?role={role}").json["csrf_token"]
    return {"X-CSRF-Token": token}


# The API.


def test_the_config_reports_no_channel_by_default(browser):
    _, client = browser
    _as(client, "admin")
    assert client.get("/dashboard/api/kudos/config").json["channel_id"] == ""


def test_a_chosen_channel_survives_a_save_and_a_reload(browser):
    _, client = browser
    headers = _as(client, "admin")
    saved = client.post(
        "/dashboard/api/kudos/config",
        json={"emoji": "☕", "daily_allowance": 4, "channel_id": "C0KUDOS"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.data
    assert saved.json["channel_id"] == "C0KUDOS"
    reloaded = client.get("/dashboard/api/kudos/config").json
    assert reloaded == {"emoji": "☕", "daily_allowance": 4, "token_auto": False, "channel_id": "C0KUDOS"}


def test_an_empty_channel_clears_it(browser):
    _, client = browser
    headers = _as(client, "admin")
    client.post("/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": "C0KUDOS"}, headers=headers)
    client.post("/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": ""}, headers=headers)
    assert client.get("/dashboard/api/kudos/config").json["channel_id"] == ""


def test_a_save_without_a_channel_leaves_it_alone(browser):
    """An older client that knows nothing of the channel cannot wipe it."""
    _, client = browser
    headers = _as(client, "admin")
    client.post("/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": "C0KUDOS"}, headers=headers)
    client.post("/dashboard/api/kudos/config", json={"emoji": "🍁", "daily_allowance": 3}, headers=headers)
    assert client.get("/dashboard/api/kudos/config").json["channel_id"] == "C0KUDOS"


@pytest.mark.parametrize("channel", ["#kudos", "kudos", "U0PERSON", "C0 KUDOS"])
def test_a_channel_that_is_not_a_channel_id_is_refused(browser, channel):
    app, client = browser
    headers = _as(client, "admin")
    response = client.post("/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": channel}, headers=headers)
    assert response.status_code == 400
    assert app.extensions["browser_test_data"].kudos_config["channel_id"] == ""


# Who may change it: the same people who may change the token and allowance.


def test_a_kudos_admin_can_choose_the_channel(browser):
    app, client = browser
    app.extensions["browser_test_data"].grants["U_LEAD"] = {"kudos"}
    headers = _as(client, "feature-admin")
    response = client.post(
        "/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": "C0KUDOS"}, headers=headers
    )
    assert response.status_code == 200, response.data
    assert response.json["channel_id"] == "C0KUDOS"


@pytest.mark.parametrize("role", ["member", "standup-admin"])
def test_anyone_else_cannot(browser, role):
    app, client = browser
    headers = _as(client, role)
    response = client.post(
        "/dashboard/api/kudos/config", json={"emoji": "☕", "channel_id": "C0KUDOS"}, headers=headers
    )
    assert response.status_code == 403
    assert app.extensions["browser_test_data"].kudos_config["channel_id"] == ""


def test_a_member_can_read_it(browser):
    _, client = browser
    _as(client, "member")
    response = client.get("/dashboard/api/kudos/config")
    assert response.status_code == 200
    assert "channel_id" in response.json


# The database layer.


def _fake_conn(monkeypatch, fetchone):
    import src.modules.kudos.db as kdb

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def db_conn():
        yield conn

    monkeypatch.setattr(kdb, "db_conn", db_conn)
    return kdb, cur


def test_get_config_reads_the_channel(monkeypatch):
    kdb, _ = _fake_conn(monkeypatch, ("☕", 5, False, "C0KUDOS"))
    assert kdb.get_config("T1")["channel_id"] == "C0KUDOS"


def test_get_config_turns_a_null_channel_into_an_empty_one(monkeypatch):
    kdb, _ = _fake_conn(monkeypatch, ("☕", 5, False, None))
    assert kdb.get_config("T1")["channel_id"] == ""


def test_get_config_defaults_to_no_channel_without_a_row(monkeypatch):
    kdb, _ = _fake_conn(monkeypatch, None)
    assert kdb.get_config("T1")["channel_id"] == ""


def test_set_config_keeps_the_channel_when_none_is_given(monkeypatch):
    kdb, cur = _fake_conn(monkeypatch, ("☕", 5, False, "C0KUDOS"))
    result = kdb.set_config("T1", "☕", 5)
    sql, params = cur.execute.call_args.args
    assert params == ("T1", "☕", 5, None)
    assert "COALESCE(EXCLUDED.channel_id, kudos_config.channel_id)" in sql
    assert result["channel_id"] == "C0KUDOS"


def test_set_config_passes_a_chosen_channel(monkeypatch):
    kdb, cur = _fake_conn(monkeypatch, ("☕", 5, False, "C0NEW"))
    kdb.set_config("T1", "☕", 5, "C0NEW")
    assert cur.execute.call_args.args[1] == ("T1", "☕", 5, "C0NEW")


def test_the_migration_adds_the_column():
    sql = (MIGRATIONS / "055_kudos_channel.sql").read_text()
    assert "ALTER TABLE kudos_config ADD COLUMN IF NOT EXISTS channel_id TEXT" in sql
