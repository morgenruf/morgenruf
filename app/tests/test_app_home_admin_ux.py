"""App Home shows standup management only to people who may manage standups.

Members who could not create a standup were offered the button anyway and got a
refusal DM in the Messages tab. The edit button for today's answers started a
brand new standup instead of editing the one sent.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("slack_bolt", MagicMock())

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]

import src.modules.standup.blocks as blocks  # noqa: E402


def _action_ids(view: dict) -> list[str]:
    ids = []
    for block in view["blocks"]:
        if block.get("accessory"):
            ids.append(block["accessory"].get("action_id"))
        for el in block.get("elements", []) or []:
            if isinstance(el, dict) and el.get("action_id"):
                ids.append(el["action_id"])
    return ids


def _text(view: dict) -> str:
    return " ".join(str(b.get("text", "")) for b in view["blocks"])


def test_member_without_standups_is_pointed_at_an_admin():
    view = blocks.app_home_view(standups=[], user_id="U1", is_admin=False, admin_contact="UINST")
    assert "open_create_standup" not in _action_ids(view)
    assert "open_configure_mode" not in _action_ids(view)
    assert "<@UINST>" in _text(view)


def test_member_without_known_admin_gets_a_generic_pointer():
    view = blocks.app_home_view(standups=[], user_id="U1", is_admin=False)
    assert "a workspace admin" in _text(view)


def test_standup_admin_gets_create_and_settings():
    view = blocks.app_home_view(standups=[], user_id="U1", is_admin=True)
    ids = _action_ids(view)
    assert "open_create_standup" in ids
    assert "open_configure_mode" in ids


def test_edit_after_answering_edits_the_answer():
    card = {
        "standup_id": "7",
        "standup_name": "Team Standup",
        "channel_id": "C1",
        "active": True,
        "user_responded_today": True,
        "user_last_response_id": 99,
    }
    view = blocks.app_home_view(standups=[card], user_id="U1")
    edit = [
        el
        for b in view["blocks"]
        for el in b.get("elements", []) or []
        if isinstance(el, dict) and el.get("action_id") == "standup_edit"
    ]
    assert edit and edit[0]["value"] == "99"
    assert edit[0]["text"]["text"].endswith("Edit my answers")
    assert "start_standup_now" not in _action_ids(view)


def test_support_and_dashboard_are_separate_links(monkeypatch):
    monkeypatch.setenv("APP_URL", "https://standups.example.com")
    view = blocks.app_home_view(standups=[], user_id="U1")
    urls = {
        el["action_id"]: el.get("url")
        for b in view["blocks"]
        for el in b.get("elements", []) or []
        if isinstance(el, dict) and el.get("action_id")
    }
    assert urls["open_dashboard"] == "https://standups.example.com/dashboard"
    assert urls["open_support"] == "https://github.com/morgenruf/morgenruf/issues"
    monkeypatch.setenv("APP_URL", "https://api.morgenruf.dev")
    view = blocks.app_home_view(standups=[], user_id="U1")
    support = [
        el["url"] for b in view["blocks"] for el in b.get("elements", []) or [] if el.get("action_id") == "open_support"
    ]
    assert support == ["https://morgenruf.dev/support/"]


def test_previous_standups_use_the_standups_own_questions_and_short_dates():
    from datetime import date

    rows = [{"standup_date": date(2026, 9, 29), "yesterday": "Shipped", "today": "", "blockers": "None"}]
    modal = blocks.previous_standups_modal(rows, "Daily", ["What shipped?", "What next?", "Stuck?"])
    text = " ".join(str(b.get("text", "")) for b in modal["blocks"])
    assert "Tue 29 Sep" in text
    assert "What shipped?" in text and "Yesterday" not in text
    assert "n/a" in text
    assert "—" not in text
