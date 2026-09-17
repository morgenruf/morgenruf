"""Per-workspace module toggles and the activation they drive."""

from __future__ import annotations

import pathlib
import re

from src.core.modules import ModuleSpec, NavItem, active_modules


def spec(name, scopes=(), default_enabled=True, nav=()):
    return ModuleSpec(
        name=name,
        required_scopes=scopes,
        migrations_dir=None,
        register_slack=None,
        register_routes=None,
        plan_jobs=None,
        claim_dm=None,
        purge=None,
        nav=nav,
        default_enabled=default_enabled,
    )


REGISTRY = (
    spec("standup", nav=(NavItem("Standups", "/"),)),
    spec("connect", scopes=("mpim:write",), default_enabled=False, nav=(NavItem("Connect", "/m/connect/"),)),
)


def test_connect_is_hidden_without_the_scope():
    result = active_modules(REGISTRY, granted_scopes=set(), settings={"connect": True}, allowlist=None)
    assert [m.name for m in result] == ["standup"]


def test_connect_appears_once_the_scope_is_granted_and_it_is_enabled():
    result = active_modules(REGISTRY, granted_scopes={"mpim:write"}, settings={"connect": True}, allowlist=None)
    assert [m.name for m in result] == ["standup", "connect"]


def test_connect_stays_off_by_default_even_with_the_scope():
    result = active_modules(REGISTRY, granted_scopes={"mpim:write"}, settings={}, allowlist=None)
    assert [m.name for m in result] == ["standup"]


def test_nav_comes_from_active_modules_only():
    result = active_modules(REGISTRY, granted_scopes=set(), settings={}, allowlist=None)
    labels = [item.label for m in result for item in m.nav]
    assert labels == ["Standups"]


MIGRATION = pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "migrations" / "030_workspace_modules.sql"


def test_the_migration_is_additive_only():
    sql = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS workspace_modules" in sql
    # ON DELETE CASCADE is a constraint clause, not a destructive statement,
    # so match statements rather than bare keywords.
    forbidden = re.compile(r"\b(DROP\s+\w+|DELETE\s+FROM|UPDATE\s+\w+\s+SET)\b", re.IGNORECASE)
    assert not forbidden.search(sql), "migration is not additive only"


def test_the_table_cascades_on_uninstall():
    """Uninstall must not leave orphaned toggle rows behind."""
    sql = MIGRATION.read_text()
    assert "REFERENCES installations(team_id) ON DELETE CASCADE" in sql


DASHBOARD = pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "dashboard.py"


def _client(monkeypatch, registry, granted=(), settings=None, role="admin"):
    """A Flask app serving the dashboard blueprint with a stubbed registry.

    The db handle is patched on src.core.dashboard itself, not on src.core.db.
    Other test modules import the dashboard with a mocked database, so
    dashboard.db is not guaranteed to be the real module object, and patching
    the module would leave the code under test reading a different one.
    """
    from unittest.mock import MagicMock

    import src.core.dashboard as dashboard_mod
    import src.modules
    from flask import Flask

    monkeypatch.setattr(src.modules, "REGISTRY", registry, raising=False)

    fake_db = MagicMock()
    fake_db.granted_scopes.return_value = set(granted)
    fake_db.module_settings.return_value = settings or {}
    fake_db.has_scopes.side_effect = lambda t, req: set(req).issubset(set(granted))
    fake_db.get_member_role.return_value = role
    monkeypatch.setattr(dashboard_mod, "db", fake_db)

    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(dashboard_mod.dashboard_bp)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["team_id"] = "T1"
        sess["user_id"] = "U1"
    return client, fake_db


def test_enabling_a_module_without_its_scopes_returns_409(monkeypatch):
    """A silent no-op would look like a working toggle that does nothing."""
    registry = (spec("connect", scopes=("mpim:write",), default_enabled=False),)
    client, _ = _client(monkeypatch, registry, granted=())
    resp = client.post("/dashboard/api/modules/connect", json={"enabled": True})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "missing_scopes"
    assert body["required"] == ["mpim:write"]
    assert body["reauthorise_url"] == "/install"


def test_enabling_a_module_with_its_scopes_succeeds(monkeypatch):
    registry = (spec("connect", scopes=("mpim:write",), default_enabled=False),)
    client, _ = _client(monkeypatch, registry, granted=("mpim:write",))
    resp = client.post("/dashboard/api/modules/connect", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.get_json() == {"module": "connect", "enabled": True}


def test_an_unknown_module_is_404(monkeypatch):
    client, _ = _client(monkeypatch, (spec("standup"),))
    resp = client.post("/dashboard/api/modules/nope", json={"enabled": True})
    assert resp.status_code == 404


def test_disabling_never_needs_scopes(monkeypatch):
    """You must always be able to turn a module off, scopes or not."""
    registry = (spec("connect", scopes=("mpim:write",), default_enabled=False),)
    client, _ = _client(monkeypatch, registry, granted=())
    resp = client.post("/dashboard/api/modules/connect", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is False


def test_core_reads_the_registry_lazily():
    """core must not gain an import-time dependency on the modules package."""
    src = DASHBOARD.read_text()
    for line in src.splitlines():
        if line.startswith(("import ", "from ")) and "src.modules" in line:
            raise AssertionError(f"core/dashboard.py imports modules at import time: {line}")
