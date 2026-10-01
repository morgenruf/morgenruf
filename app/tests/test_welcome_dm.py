"""The welcome DM leads with the quick start.

Most outside workspaces that removed the app never created a standup, so the
first message after install puts "Start a standup" first, above the email
offer, instead of sending people to the Home tab to find a form.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def welcome_blocks():
    from src.core.oauth import _welcome_blocks

    return _welcome_blocks()


def test_welcome_dm_has_the_quick_start_button_before_the_email_offer(welcome_blocks):
    ids = [b.get("block_id") for b in welcome_blocks if b["type"] == "actions"]
    assert ids[0] == "quickstart"
    assert ids[1] == "email_offer"


def test_the_text_says_what_to_do_now(welcome_blocks):
    text = welcome_blocks[0]["text"]["text"]
    assert "Start your team's standup now" in text
    assert "/morgenruf help" in text


def test_the_callback_sends_these_blocks():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "src/core/oauth.py").read_text()
    assert "blocks=_welcome_blocks()" in src
