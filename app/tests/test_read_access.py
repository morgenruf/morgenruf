"""What a member can read about other people.

Writes were guarded; reads mostly were not, which went unnoticed while only
the installer could sign in. Once members could sign in, any of them could
read every coworker's standup answers on Today (private channels included),
per-person analytics, and who skipped or opted out of coffee chats.

The rule now: a member reads their own data, standups they could see in
Slack anyway, and things already public in Slack (kudos, polls, pulse
aggregates). Per-person views of others need the feature's admin grant, and
workspace plumbing (webhooks, API keys) needs a workspace admin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.browser_fixtures import create_test_app
from tests.support import RouteDeclarations

APP = Path(__file__).resolve().parents[1]

# Every GET route a plain member may call, and why. Anything not here must
# carry an admin guard; a new route fails the test below until decided.
MEMBER_READABLE = {
    "/dashboard/api/me": "their own session",
    "/dashboard/api/profile": "their own profile",
    "/dashboard/api/modules": "which features are on",
    "/dashboard/api/channels": "channel names for pickers",
    "/dashboard/api/templates": "question templates",
    "/dashboard/api/members": "the directory: names and avatars, no email unless admin",
    "/dashboard/api/standups": "only standups they are in, can see in Slack, or manage",
    "/dashboard/api/reports": "answers from those standups only",
    "/dashboard/api/export/csv": "answers from those standups only",
    "/dashboard/api/ai-summary": "whether AI summaries are configured",
    "/dashboard/api/celebrations/settings": "channel and time, no dates",
    "/dashboard/api/celebrations/holidays": "the company holiday list",
    "/dashboard/api/connect/programs": "which coffee programmes exist",
    "/dashboard/api/connect/programs/<int:program_id>/rounds": "round totals, no names",
    "/dashboard/api/connect/zoom": "whether Zoom is set up",
    "/dashboard/api/kudos": "kudos are posted publicly in Slack",
    "/dashboard/api/kudos/leaderboard": "kudos are posted publicly in Slack",
    "/dashboard/api/kudos/givers": "kudos are posted publicly in Slack",
    "/dashboard/api/kudos/config": "the kudos token and allowance",
    "/dashboard/api/polls": "polls in channels they can see, anonymous ones stay anonymous",
    "/dashboard/api/pulse/settings": "schedule only",
    "/dashboard/api/pulse/trend": "team aggregates with minimum group sizes",
}


def _open_reads():
    files = [APP / "src/core/dashboard.py"] + sorted((APP / "src/modules").glob("*/dashboard.py"))
    out = []
    for f in files:
        for path, opts, decorators, fn in RouteDeclarations().findall(f.read_text()):
            if "'GET'" not in opts or not path.startswith("/dashboard/api"):
                continue
            if "_admin_required" in decorators:
                continue
            out.append((path, fn))
    return out


def test_every_member_readable_route_was_decided():
    undecided = [f"{path} ({fn})" for path, fn in _open_reads() if path not in MEMBER_READABLE]
    assert not undecided, "GET routes open to any member that nobody decided on:\n  " + "\n  ".join(undecided)


def test_the_scan_finds_routes():
    assert len(_open_reads()) >= 10


# Per-person data about others: (path, the grant that opens it, or None for workspace admin)
SENSITIVE = [
    ("/dashboard/api/today", "standup"),
    ("/dashboard/api/insights", "standup"),
    ("/dashboard/api/analytics", "standup"),
    ("/dashboard/api/stats", "standup"),
    ("/dashboard/api/rules", "standup"),
    ("/dashboard/api/connect/rounds/1/matches", "connect"),
    ("/dashboard/api/connect/programs/1/members", "connect"),
    ("/dashboard/api/connect/programs/1/participation", "connect"),
    ("/dashboard/api/webhooks", None),
    ("/dashboard/api/webhooks/events", None),
    ("/dashboard/api/webhooks/1/deliveries", None),
    ("/dashboard/api/mcp/keys", None),
]


@pytest.fixture
def app(monkeypatch):
    return create_test_app(monkeypatch)


def _as(app, role):
    client = app.test_client()
    client.post(f"/__test__/session?role={role}")
    return client


@pytest.mark.parametrize("path,grant", SENSITIVE, ids=[p for p, _ in SENSITIVE])
def test_a_member_is_refused(app, path, grant):
    assert _as(app, "member").get(path).status_code == 403


@pytest.mark.parametrize("path,grant", SENSITIVE, ids=[p for p, _ in SENSITIVE])
def test_the_right_admin_gets_in(app, path, grant):
    # U_LEAD holds the standup and connect grants, and is not a workspace admin.
    lead = _as(app, "feature-admin").get(path).status_code
    admin = _as(app, "admin").get(path).status_code
    assert admin != 403
    if grant:
        assert lead != 403
    else:
        assert lead == 403
