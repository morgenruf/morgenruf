"""A plain member must not be able to change the workspace.

Two roles have existed since migration 008 and only thirteen routes used them.
Fourteen mutating routes were reachable by anyone with a session, including
publishing the team's standups to an unauthenticated URL, minting a
workspace-read API key, and deleting the standup schedule.

The Connect module was gated correctly, which is what made the gap visible:
the newest module enforced and core did not.
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
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

# Every mutating route a member must be refused, with what it would let them do.
GUARDED = [
    ("POST", "/dashboard/api/feed-token", "publish the team's standups publicly"),
    ("DELETE", "/dashboard/api/feed-token", "revoke the public feed"),
    ("POST", "/dashboard/api/mcp/keys", "mint a workspace-read API key"),
    ("DELETE", "/dashboard/api/mcp/keys/1", "delete someone's API key"),
    ("POST", "/dashboard/api/rules", "add an automation rule"),
    ("DELETE", "/dashboard/api/rules/1", "delete an automation rule"),
    ("POST", "/dashboard/api/standups", "create a standup"),
    ("PUT", "/dashboard/api/standups/1", "change questions, participants, digest address"),
    ("DELETE", "/dashboard/api/standups/1", "delete the team's standup"),
    ("POST", "/dashboard/api/webhooks", "add a webhook"),
    ("PATCH", "/dashboard/api/webhooks/1", "repoint a webhook"),
    ("DELETE", "/dashboard/api/webhooks/1", "delete a webhook"),
    ("POST", "/dashboard/api/webhooks/1/rotate", "rotate a signing secret and break the consumer"),
    ("POST", "/dashboard/api/webhooks/1/test", "send data to an external url"),
]


@pytest.fixture()
def member_client(monkeypatch):
    flask_app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "../src/core/templates"))
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    flask_app.register_blueprint(dashboard.dashboard_bp)

    db = MagicMock()
    db.get_member_role.return_value = "member"
    monkeypatch.setattr(dashboard, "db", db)

    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["team_id"] = "T123"
        sess["user_id"] = "U_MEMBER"
    return client


class TestAMemberIsRefused:
    @pytest.mark.parametrize("method,path,what", GUARDED, ids=[g[1] + ":" + g[0] for g in GUARDED])
    def test_refused(self, member_client, method, path, what):
        resp = member_client.open(path, method=method, json={})
        assert resp.status_code == 403, f"a member could {what} ({method} {path})"

    def test_reading_is_still_allowed(self, member_client):
        # Roles gate changing things, not looking at them.
        assert member_client.get("/dashboard/api/standups").status_code == 200


class TestNoMutatingRouteIsLeftOpen:
    """The list above is a snapshot; this is the rule.

    A new mutating route added without a guard fails here rather than waiting
    to be noticed in an audit.
    """

    ROUTE = re.compile(r'@\w+\.route\(\s*["\']([^"\']+)["\']([^)]*)\)\s*((?:@[\w_]+(?:\([^)]*\))?\s*)*)def\s+(\w+)')

    def _open_mutating_routes(self):
        files = [APP / "src/core/dashboard.py"] + sorted((APP / "src/modules").glob("*/dashboard.py"))
        out = []
        for f in files:
            for path, opts, decorators, fn in self.ROUTE.findall(f.read_text()):
                methods = re.search(r"methods\s*=\s*\[([^\]]*)\]", opts)
                methods = {x.strip().strip("\"'") for x in methods.group(1).split(",")} if methods else {"GET"}
                if not (methods & MUTATING):
                    continue
                if "_admin_required" not in decorators:
                    out.append(f"{sorted(methods & MUTATING)} {path} ({fn})")
        return out

    def test_every_mutating_route_requires_admin(self):
        open_routes = self._open_mutating_routes()
        assert not open_routes, "mutating routes any member can reach:\n  " + "\n  ".join(open_routes)

    def test_the_scan_actually_finds_routes(self):
        # Guard against a regex change making this pass vacuously.
        files = (APP / "src/core/dashboard.py").read_text()
        assert len(self.ROUTE.findall(files)) > 20
