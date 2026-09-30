"""A kudos is reposted under the bot's name, so what the giver typed and the
token an admin chose must not turn into a broadcast or a disguised link."""

from __future__ import annotations

import pytest
from src.modules.kudos import db as kdb
from src.modules.kudos.handlers import kudos_card, recipient_card, safe_reason

from tests.browser_fixtures import create_test_app


def _texts(blocks):
    return " ".join(b["text"]["text"] for b in blocks if b.get("text"))


@pytest.mark.parametrize(
    ("typed", "shown"),
    [
        ("<!channel> thanks", "@channel thanks"),
        ("<!here|here> and <!everyone>", "@here and @everyone"),
        ("<!subteam^S123|@devs> nice", "@devs nice"),
        ("see <https://evil.test/x|sso.acme.com>", "see <https://evil.test/x>"),
        ("mail <mailto:a@evil.test|boss@acme.com>", "mail <mailto:a@evil.test>"),
    ],
)
def test_broadcasts_and_disguised_links_are_defused(typed, shown):
    assert safe_reason(typed) == shown


def test_mentions_channels_and_plain_links_survive():
    typed = "<@U123|sam> fixed it in <#C1|eng>, see <https://ok.test/pr/1>"
    assert safe_reason(typed) == typed


def test_both_cards_carry_the_defused_reason():
    _, blocks = kudos_card("UA", "UB", "<!channel> <https://evil.test|acme.com>", "🍁")
    _, dm = recipient_card("UA", "<!channel> <https://evil.test|acme.com>", "🍁")
    for rendered in (_texts(blocks), _texts(dm)):
        assert "<!channel>" not in rendered
        assert "|acme.com>" not in rendered
        assert "<https://evil.test>" in rendered


@pytest.mark.parametrize(
    "token", ["🍁", "☕", "👍🏽", "🧑‍💻", ":tada:", ":morgenruf:", ":+1:", ":v::skin-tone-2:", "1️⃣"]
)
def test_emoji_tokens_that_are_allowed(token):
    assert kdb.valid_emoji(token)


@pytest.mark.parametrize(
    "token", ["", "<!channel>", "<https://x|y>", "kudos", ":ta da:", "*bold*", "🍁<", "🍁 🍁", "x" * 17, ":a:" * 6]
)
def test_emoji_tokens_that_are_refused(token):
    assert not kdb.valid_emoji(token)


def test_a_bad_saved_token_falls_back_to_the_default(monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = ("<!channel>", 5, False, "")
    conn = MagicMock()
    conn.cursor.return_value = cur

    @contextmanager
    def db_conn():
        yield conn

    monkeypatch.setattr(kdb, "db_conn", db_conn)
    assert kdb.get_config("T1")["emoji"] == kdb.DEFAULT_EMOJI


def test_the_settings_api_refuses_markup_as_a_token(monkeypatch):
    app = create_test_app(monkeypatch)
    client = app.test_client()
    csrf = client.post("/__test__/session?role=admin").json["csrf_token"]
    response = client.post("/dashboard/api/kudos/config", json={"emoji": "<!channel>"}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 400
    assert app.extensions["browser_test_data"].kudos_config["emoji"] == "🍁"
