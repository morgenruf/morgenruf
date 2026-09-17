"""granted_scopes records what Slack actually granted, not what we asked for."""

from __future__ import annotations

import pathlib
import re
from unittest.mock import patch

# Import the module rather than the functions. Other test modules replace
# src.core.db in sys.modules, so a name bound at import time and a patch
# target resolved later can end up referring to two different modules.
import src.core.db as core_db


def test_parse_splits_the_comma_separated_slack_field():
    assert core_db.parse_scope_field("chat:write,im:write,users:read") == ["chat:write", "im:write", "users:read"]


def test_parse_handles_an_empty_field():
    assert core_db.parse_scope_field("") == []
    assert core_db.parse_scope_field(None) == []


def test_parse_strips_whitespace():
    assert core_db.parse_scope_field("chat:write, im:write") == ["chat:write", "im:write"]


def test_has_scopes_is_true_when_all_are_present():
    with patch.object(core_db, "granted_scopes", return_value={"mpim:write", "chat:write"}):
        assert core_db.has_scopes("T1", ["mpim:write"]) is True


def test_has_scopes_is_false_when_one_is_missing():
    with patch.object(core_db, "granted_scopes", return_value={"chat:write"}):
        assert core_db.has_scopes("T1", ["mpim:write", "chat:write"]) is False


def test_requiring_nothing_is_always_true():
    """Standup declares no required scopes and must never be gated."""
    with patch.object(core_db, "granted_scopes", return_value=set()):
        assert core_db.has_scopes("T1", []) is True


def test_an_unknown_scope_set_gates_modules_that_need_scopes():
    """A workspace installed before this column existed has NULL, read as empty.

    Failing closed is the safe direction: the module stays off until an admin
    re-authorises.
    """
    with patch.object(core_db, "granted_scopes", return_value=set()):
        assert core_db.has_scopes("T1", ["mpim:write"]) is False


MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "migrations" / "029_granted_scopes.sql"


def test_the_migration_is_additive_only():
    """Rollback must stay a plain image revert."""
    sql = MIGRATION.read_text()
    assert "ADD COLUMN IF NOT EXISTS" in sql
    forbidden = re.compile(r"\b(DROP|ALTER\s+COLUMN|UPDATE|DELETE)\b", re.IGNORECASE)
    assert not forbidden.search(sql), "migration is not additive only"


def test_oauth_records_the_granted_scope_field():
    """The value must come from the response, never from the requested list."""
    oauth_src = (pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "oauth.py").read_text()
    assert 'parse_scope_field(resp.get("scope"))' in oauth_src
