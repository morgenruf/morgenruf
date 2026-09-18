"""One person can run the standups without running the workspace.

Roles were workspace-wide: a team lead who should own the standup schedule
had to be handed webhooks, API keys and the public feed as well. In practice
nobody was promoted, so one admin did everything and every other request went
through them.

A grant is per feature. A workspace admin still implies every feature, so
nothing that worked before changed.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
from unittest.mock import MagicMock

import pytest

if isinstance(sys.modules.get("pytz"), MagicMock):
    del sys.modules["pytz"]
for mod in ("psycopg2", "psycopg2.extras", "psycopg2.pool", "slack_sdk", "slack_bolt", "markupsafe"):
    sys.modules.setdefault(mod, MagicMock())

_prior_db = sys.modules.get("src.core.db")
_prior_oauth = sys.modules.get("src.core.oauth")
sys.modules["src.core.db"] = MagicMock()
sys.modules["src.core.oauth"] = MagicMock()

import src.core.dashboard as dashboard  # noqa: E402
from flask import Flask  # noqa: E402

if _prior_db is not None:
    sys.modules["src.core.db"] = _prior_db
else:
    sys.modules.pop("src.core.db", None)
if _prior_oauth is not None:
    sys.modules["src.core.oauth"] = _prior_oauth
else:
    sys.modules.pop("src.core.oauth", None)

APP = pathlib.Path(__file__).resolve().parent.parent


def _client(monkeypatch, role="member", grants=(), user_id="U_LEAD"):
    grants = set(grants)
    flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "../src/core/templates"))
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)

    db = MagicMock()
    db.get_member_role.return_value = role
    db.count_admins.return_value = 2
    db.module_admin_grants.return_value = grants
    db.team_module_admins.return_value = {user_id: grants} if grants else {}
    db.can_administer.side_effect = lambda t, u, module=None: role == "admin" or (
        module is not None and module in grants
    )
    # Real enough to serialise back out of the update route.
    db.update_standup_schedule.return_value = {
        "id": 1,
        "team_id": "T123",
        "name": "Daily",
        "channel_id": "C1",
        "questions": ["a"],
        "participants": [],
        "schedule_days": "mon,tue",
    }
    db.get_workspace_config.return_value = {}
    monkeypatch.setattr(dashboard, "db", db)

    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = user_id
    return client, db


# What a standup grant is for, and what it must not reach.
OWNED = [
    ("POST", "/dashboard/api/standups"),
    ("PUT", "/dashboard/api/standups/1"),
    ("DELETE", "/dashboard/api/standups/1"),
    ("POST", "/dashboard/api/rules"),
    ("DELETE", "/dashboard/api/rules/1"),
]

NOT_OWNED = [
    ("POST", "/dashboard/api/mcp/keys", "mint an API key"),
    ("POST", "/dashboard/api/feed-token", "publish the workspace's standups"),
    ("POST", "/dashboard/api/webhooks", "send standup data to an external url"),
    ("PUT", "/dashboard/api/members/U_X/role", "promote themselves"),
    ("POST", "/dashboard/api/modules/connect", "turn features on and off"),
    ("PUT", "/dashboard/api/members/U_X/modules/standup", "hand the grant to someone else"),
]


class TestAStandupAdminRunsStandups:
    @pytest.mark.parametrize("method,path", OWNED, ids=[f"{m}:{p}" for m, p in OWNED])
    def test_allowed(self, monkeypatch, method, path):
        client, _ = _client(monkeypatch, grants={"standup"})
        resp = client.open(path, method=method, json={"name": "Daily", "channel_id": "C1", "questions": ["a"]})
        assert resp.status_code != 403, f"a standup admin was refused {method} {path}"

    @pytest.mark.parametrize("method,path,what", NOT_OWNED, ids=[f"{m}:{p}" for m, p, _ in NOT_OWNED])
    def test_refused_everywhere_else(self, monkeypatch, method, path, what):
        client, _ = _client(monkeypatch, grants={"standup"})
        resp = client.open(path, method=method, json={"role": "admin"})
        assert resp.status_code == 403, f"a standup admin could {what} ({method} {path})"

    def test_a_workspace_route_says_admin(self, monkeypatch):
        client, _ = _client(monkeypatch, grants={"standup"})
        resp = client.post("/dashboard/api/modules/connect", json={})
        assert "Admin required" in resp.get_json()["error"]

    def test_a_feature_route_says_what_to_ask_for(self, monkeypatch):
        """"You need to administer connect" is the column name, not a feature."""
        client, _ = _client(monkeypatch, grants={"connect"})
        resp = client.post("/dashboard/api/standups", json={})
        assert resp.get_json()["error"] == "Ask an admin to put you in charge of Standups"

    def test_the_label_comes_from_the_registry(self):
        # So core keeps no list of feature names of its own.
        src = (APP / "src/core/dashboard.py").read_text()
        fn = src[src.index("def _no_grant_message") :][:600]
        assert "REGISTRY" in fn and "nav[0].label" in fn


class TestAGrantIsNotAWayUp:
    """The standup form also carries the public feed switch."""

    def test_a_standup_admin_cannot_publish_through_the_form(self, monkeypatch):
        client, db = _client(monkeypatch, grants={"standup"})
        resp = client.put(
            "/dashboard/api/standups/1",
            json={"name": "Daily", "channel_id": "C1", "questions": ["a"], "feed_public": True},
        )
        assert resp.status_code == 200
        for call in db.upsert_workspace_config.call_args_list:
            assert "feed_public" not in call.kwargs, "a standup admin published the workspace's standups"

    def test_a_workspace_admin_still_can(self, monkeypatch):
        client, db = _client(monkeypatch, role="admin")
        client.put(
            "/dashboard/api/standups/1",
            json={"name": "Daily", "channel_id": "C1", "questions": ["a"], "feed_public": True},
        )
        assert any("feed_public" in c.kwargs for c in db.upsert_workspace_config.call_args_list)

    def test_the_other_workspace_settings_still_save(self, monkeypatch):
        # Everything else on that form is part of running standups.
        client, db = _client(monkeypatch, grants={"standup"})
        client.put(
            "/dashboard/api/standups/1",
            json={"name": "Daily", "channel_id": "C1", "questions": ["a"], "manager_email": "lead@example.com"},
        )
        assert any("manager_email" in c.kwargs for c in db.upsert_workspace_config.call_args_list)


class TestOnlyAWorkspaceAdminHandsOutGrants:
    def test_granting(self, monkeypatch):
        client, db = _client(monkeypatch, role="admin")
        resp = client.put("/dashboard/api/members/U_HR/modules/connect")
        assert resp.status_code == 200
        db.grant_module_admin.assert_called_once()
        assert db.grant_module_admin.call_args[0][:3] == ("T123", "U_HR", "connect")

    def test_revoking(self, monkeypatch):
        client, db = _client(monkeypatch, role="admin")
        assert client.delete("/dashboard/api/members/U_HR/modules/connect").status_code == 200
        db.revoke_module_admin.assert_called_once()

    def test_an_unknown_feature_is_refused(self, monkeypatch):
        client, db = _client(monkeypatch, role="admin")
        assert client.put("/dashboard/api/members/U_HR/modules/billing").status_code == 404
        db.grant_module_admin.assert_not_called()


class TestThePageKnowsWhoCanDoWhat:
    def test_me_reports_the_grants(self, monkeypatch):
        client, _ = _client(monkeypatch, grants={"connect", "kudos"})
        body = client.get("/dashboard/api/me").get_json()
        assert body["role"] == "member"
        assert body["module_admin"] == ["connect", "kudos"]

    def test_an_admin_needs_no_grants_listed(self, monkeypatch):
        client, _ = _client(monkeypatch, role="admin")
        assert client.get("/dashboard/api/me").get_json()["role"] == "admin"

    def test_the_members_list_carries_each_persons_grants(self):
        # Rendered by the members table, so it has to come down with the row.
        src = (APP / "src/core/dashboard.py").read_text()
        assert '"module_admin": sorted(grants.get(uid, ()))' in src

    def test_the_grants_survive_slack_being_down(self):
        """The members list falls back to the database, and the page renders
        the same cards from it."""
        src = (APP / "src/core/dashboard.py").read_text()
        fallback = src[src.index("# Fall back to DB members") :][:900]
        assert '"module_admin": sorted(grants.get(r["user_id"], ()))' in fallback

    def test_the_members_page_offers_them(self):
        markup = (APP / "src/core/templates/dashboard.html").read_text()
        assert "toggleModuleAdmin" in markup
        # A toggle, so it says what it is: pressed state, and one request at a
        # time rather than two opposite ones racing on a slow link.
        assert "aria-pressed" in markup
        assert "aria-busy" in markup
        # "Runs" over three switched-off chips would read as a claim.
        assert "Put in charge of" in markup
        assert "'/members/' + userId + '/modules/' + module" in markup
        # And an admin's card says why it has no switches.
        assert "Runs every feature" in markup


class TestEveryModuleRouteNamesItsFeature:
    """A module route gated workspace-wide cannot be delegated at all."""

    ROUTE = re.compile(r'@\w+\.route\(\s*["\']([^"\']+)["\']([^)]*)\)\s*((?:@[\w_]+(?:\([^)]*\))?\s*)*)def\s+(\w+)')
    MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

    @pytest.mark.parametrize("module", ["connect", "kudos"])
    def test_named(self, module):
        f = APP / f"src/modules/{module}/dashboard.py"
        wrong = []
        for path, opts, decorators, fn in self.ROUTE.findall(f.read_text()):
            methods = re.search(r"methods\s*=\s*\[([^\]]*)\]", opts)
            methods = {x.strip().strip("\"'") for x in methods.group(1).split(",")} if methods else {"GET"}
            if not (methods & self.MUTATING) or "_admin_required" not in decorators:
                continue
            if f'_admin_required("{module}")' not in decorators:
                wrong.append(f"{path} ({fn})")
        assert not wrong, f"{module} routes that only a workspace admin can reach:\n  " + "\n  ".join(wrong)

    def test_the_scan_finds_something(self):
        f = (APP / "src/modules/connect/dashboard.py").read_text()
        assert len(self.ROUTE.findall(f)) > 5


class TestTheRuleItself:
    def test_an_admin_administers_everything(self, monkeypatch):
        import src.core.db as real_db

        monkeypatch.setattr(real_db, "get_member_role", lambda t, u: "admin")
        assert real_db.can_administer("T", "U") is True
        assert real_db.can_administer("T", "U", "connect") is True

    def test_a_grant_covers_one_feature_only(self, monkeypatch):
        import src.core.db as real_db

        monkeypatch.setattr(real_db, "get_member_role", lambda t, u: "member")
        monkeypatch.setattr(real_db, "module_admin_grants", lambda t, u: {"connect"})
        assert real_db.can_administer("T", "U", "connect") is True
        assert real_db.can_administer("T", "U", "standup") is False

    def test_a_route_that_names_no_feature_stays_workspace_admin(self, monkeypatch):
        import src.core.db as real_db

        monkeypatch.setattr(real_db, "get_member_role", lambda t, u: "member")
        monkeypatch.setattr(real_db, "module_admin_grants", lambda t, u: {"connect", "kudos", "standup"})
        assert real_db.can_administer("T", "U") is False

    def test_the_grant_table_can_take_the_upsert(self):
        sql = (APP / "src/core/migrations/047_module_admins.sql").read_text()
        assert "UNIQUE (team_id, user_id, module)" in sql
