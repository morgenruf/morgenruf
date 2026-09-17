"""Choosing between the branded token and the plain one.

A custom emoji only renders once a workspace has imported it, so defaulting to
:morgenruf: made a new workspace post that literal text in every kudos message.
The rule here is: start plain, upgrade only on evidence, and never overrule an
admin who has chosen for themselves.
"""

from __future__ import annotations

from src.modules.kudos.token import BRAND_TOKEN, resolve, workspace_has_brand_emoji

MAPLE = "\N{MAPLE LEAF}"


class FakeClient:
    def __init__(self, emoji=None, raises=None):
        self._emoji = emoji
        self._raises = raises

    def emoji_list(self):
        if self._raises:
            raise self._raises
        return {"ok": True, "emoji": self._emoji}


# ── workspace_has_brand_emoji ────────────────────────────────────────────────


def test_the_emoji_is_found_when_the_workspace_has_it():
    assert workspace_has_brand_emoji(FakeClient({"morgenruf": "https://x/y.png"})) is True


def test_the_emoji_is_absent_when_the_workspace_has_others():
    assert workspace_has_brand_emoji(FakeClient({"partyparrot": "https://x/p.gif"})) is False


def test_an_empty_emoji_list_means_absent():
    assert workspace_has_brand_emoji(FakeClient({})) is False


def test_a_missing_scope_is_unknown_rather_than_absent():
    """Without emoji:read the call fails, and that must not read as 'deleted'."""
    assert workspace_has_brand_emoji(FakeClient(raises=RuntimeError("missing_scope"))) is None


def test_a_rate_limit_is_unknown_too():
    assert workspace_has_brand_emoji(FakeClient(raises=RuntimeError("ratelimited"))) is None


def test_a_malformed_response_is_unknown():
    assert workspace_has_brand_emoji(FakeClient(emoji=["not", "a", "dict"])) is None


# ── resolve ──────────────────────────────────────────────────────────────────


def test_a_workspace_with_the_emoji_is_upgraded():
    assert resolve(MAPLE, token_auto=True, has_brand=True) == BRAND_TOKEN


def test_a_workspace_already_upgraded_is_left_alone():
    assert resolve(BRAND_TOKEN, token_auto=True, has_brand=True) is None


def test_a_workspace_without_the_emoji_stays_plain():
    assert resolve(MAPLE, token_auto=True, has_brand=False) is None


def test_a_workspace_posting_literal_text_is_rescued():
    """If the emoji is deleted, the branded token renders as ':morgenruf:'."""
    assert resolve(BRAND_TOKEN, token_auto=True, has_brand=False) == MAPLE


def test_an_admins_own_choice_is_never_overwritten():
    assert resolve("\N{TACO}", token_auto=False, has_brand=True) is None
    assert resolve(BRAND_TOKEN, token_auto=False, has_brand=False) is None


def test_nothing_moves_while_slack_is_unreadable():
    """Unknown must change nothing, in either direction."""
    assert resolve(MAPLE, token_auto=True, has_brand=None) is None
    assert resolve(BRAND_TOKEN, token_auto=True, has_brand=None) is None
