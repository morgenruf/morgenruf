"""In-memory adapters for real browser HTTP integration tests.

Only imported by tests and the local Playwright runner. Production construction
never exposes test sessions or replaces its database/integration adapters.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone


class BrowserData:
    team_id = "T_BROWSER"
    team_name = "Northstar Studio"

    def __init__(self):
        self.reset()

    def reset(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.today = self.now.date()
        self.roles = {"U_ADMIN": "admin", "U_MEMBER": "member", "U_LEAD": "member"}
        self.grants = {"U_LEAD": {"standup", "connect"}}
        self.members = [
            {
                "user_id": user,
                "real_name": name,
                "display_name": name.split()[0].lower(),
                "email": f"{user.lower()}@example.test",
                "avatar_url": "",
                "tz": "UTC",
                "active": True,
                "on_vacation": False,
            }
            for user, name in (("U_ADMIN", "Alex Morgan"), ("U_MEMBER", "Jamie Chen"), ("U_LEAD", "Sam Rivera"))
        ]
        self.channels = [{"id": "C_ENGINEERING", "name": "engineering"}, {"id": "C_GENERAL", "name": "general"}]
        self.workspace = {
            "team_id": self.team_id,
            "standup_name": "Northstar daily update",
            "feed_public": True,
            "feed_token": "public-browser-feed",
            "manager_email": "manager@example.test",
            "bot_token": "must-never-be-public",
        }
        self.schedules = [
            {
                "id": 1,
                "team_id": self.team_id,
                "name": "Engineering standup",
                "channel_id": "C_ENGINEERING",
                "schedule_time": "09:00",
                "schedule_tz": "UTC",
                "schedule_days": "mon,tue,wed,thu,fri",
                "questions": ["What did you finish?", "What is next?", "Any blockers?"],
                "participants": [m["user_id"] for m in self.members],
                "active": True,
                "reminder_minutes": 30,
                "report_channel": "C_ENGINEERING",
                "report_time": "17:00",
                "digest_email": "",
                "digest_enabled": False,
                "nudge_missing": False,
                "nudge_minutes_before": 20,
                "post_summary": True,
                "post_to_thread": False,
                "notify_on_report": True,
            }
        ]
        self.responses = [
            {
                "id": 1,
                "team_id": self.team_id,
                "user_id": "U_ADMIN",
                "user_name": "Alex Morgan",
                "real_name": "Alex Morgan",
                "standup_date": self.today,
                "yesterday": "Shipped the onboarding improvements.",
                "today": "Finish the API contract and review the dashboard.",
                "blockers": "Waiting for design review on the settings page.",
                "has_blockers": True,
                "submitted_at": self.now,
                "mood": "great",
                "schedule_id": 1,
            }
        ]
        self.kudos = [
            {
                "id": 1,
                "team_id": self.team_id,
                "from_user": "U_MEMBER",
                "to_user": "U_ADMIN",
                "from_name": "Jamie Chen",
                "to_name": "Alex Morgan",
                "message": "Thanks for helping ship the onboarding improvements!",
                "channel_id": "C_GENERAL",
                "emoji": "🍁",
                "created_at": self.now,
            }
        ]
        self.kudos_config = {"emoji": "🍁", "daily_allowance": 5, "token_auto": True}
        self.programs = [
            {
                "id": 1,
                "team_id": self.team_id,
                "name": "Friday coffee",
                "channel_id": "C_GENERAL",
                "interval_weeks": 1,
                "day_of_week": 4,
                "hour": 10,
                "minute": 0,
                "timezone": "UTC",
                "enabled": True,
                "created_at": self.now,
                "match_working_hours": False,
                "meeting_minutes": 30,
                "meeting_link": "https://meet.example.test/team",
                "suggest_times": True,
                "use_icebreaker": True,
                "post_stats": False,
                "group_size": 2,
                "strict_group_size": False,
                "intro_tone": "hybrid",
                "video_mode": "link",
                "next_round_date": self.today + timedelta(days=3),
                "round_count": 1,
                "last_round": self.now - timedelta(days=7),
            }
        ]
        self.rounds = [
            {
                "id": 1,
                "program_id": 1,
                "team_id": self.team_id,
                "scheduled_for": self.now - timedelta(days=7),
                "state": "closed",
                "member_count": 3,
                "created_at": self.now - timedelta(days=7),
                "matches": 1,
                "met": 1,
                "missed": 0,
                "no_reply": 0,
                "undelivered": 0,
                "agreed": 1,
                "with_zoom": 0,
                "rematch_requests": 0,
            }
        ]
        self.member_states = {}
        self.hooks = [
            {
                "id": 1,
                "webhook_url": "https://hooks.example.test/standup",
                "events": ["standup.completed"],
                "secret": "whsec_existing_secret",
                "created_at": self.now,
            }
        ]
        self.keys = [
            {
                "id": 1,
                "key_prefix": "mrn_example",
                "name": "Local assistant",
                "created_at": self.now,
                "last_used_at": None,
                "active": True,
            }
        ]
        self.rules = [
            {
                "id": 1,
                "team_id": self.team_id,
                "name": "Escalate blockers",
                "trigger": "blocker_detected",
                "condition_value": None,
                "action": "dm_user",
                "action_target": "U_LEAD",
                "action_message": "Please help unblock the team.",
                "active": True,
                "created_at": self.now,
            }
        ]
        self.module_settings = {"standup": True, "connect": True, "kudos": True, "insights": True}

    def overview(self, days=7):
        dates = [(self.today - timedelta(days=i)).isoformat() for i in reversed(range(days))]
        schedule_rows = [
            {
                "schedule_id": row["id"],
                "name": row["name"],
                "occurrence_days": days,
                "participants": 3,
                "expected": days * 3,
                "completed": days * 2,
                "missed": days,
                "completion_rate": 67,
                "series": [67] * days,
            }
            for row in self.schedules
        ]
        members = [
            {
                "user_id": member["user_id"],
                "real_name": member["real_name"],
                "enrolled": True,
                "on_vacation": False,
                "expected": days,
                "completed": days if i != 1 else 0,
                "missed": 0 if i != 1 else days,
                "responses": days if i != 1 else 0,
                "completion_rate": 100 if i != 1 else 0,
                "last_standup": self.now if i != 1 else None,
                "days_with_blockers": 1 if i == 0 else 0,
                "days": [
                    {"date": d, "expected": 1, "completed": 0 if i == 1 else 1, "blocked": i == 0 and d == dates[-1]}
                    for d in dates
                ],
                "schedules": [s["name"] for s in self.schedules],
                "schedule_ids": [s["id"] for s in self.schedules],
            }
            for i, member in enumerate(self.members)
        ]
        return {
            "days": days,
            "window_days": dates,
            "expected": days * 3,
            "completed": days * 2,
            "missed": days,
            "completion_rate": 67,
            "responses": days * 2,
            "responding_members": 2,
            "total_members": 3,
            "enrolled_members": 3,
            "unenrolled_members": 0,
            "on_vacation_members": 0,
            "members": members,
            "schedules": schedule_rows,
        }

    def update(self, collection, row_id, **fields):
        row = next((item for item in collection if item["id"] == int(row_id)), None)
        if row is not None:
            row.update(fields)
        return deepcopy(row)

    def create_schedule(self, team_id, **fields):
        row = {
            **deepcopy(self.schedules[0]),
            **fields,
            "id": max((s["id"] for s in self.schedules), default=0) + 1,
            "team_id": team_id,
        }
        self.schedules.append(row)
        return deepcopy(row)

    def create_program(self, **fields):
        row = {**deepcopy(self.programs[0]), **fields, "id": max((s["id"] for s in self.programs), default=0) + 1}
        self.programs.append(row)
        return deepcopy(row)

    def create_hook(self, team_id, url, secret, events):
        row = {
            "id": max((h["id"] for h in self.hooks), default=0) + 1,
            "webhook_url": url,
            "secret": secret,
            "events": events or ["standup.completed"],
            "created_at": self.now,
        }
        self.hooks.append(row)
        return deepcopy(row)

    def update_hook(self, team_id, row_id, url=None, events=None):
        fields = {}
        if url is not None:
            fields["webhook_url"] = url
        if events is not None:
            fields["events"] = events
        return self.update(self.hooks, row_id, **fields)

    def create_key(self, team_id, name):
        key_id = max((k["id"] for k in self.keys), default=0) + 1
        self.keys.append(
            {
                "id": key_id,
                "key_prefix": f"mrn_browser_{key_id}",
                "name": name,
                "created_at": self.now,
                "last_used_at": None,
                "active": True,
            }
        )
        return f"mrn_browser_secret_{key_id}"

    def delete(self, collection, row_id):
        old = len(collection)
        collection[:] = [r for r in collection if r["id"] != int(row_id)]
        return len(collection) < old


def create_test_app(patcher=None):
    """Build real routes with explicit fake collaborators; optionally restore patches."""
    import slack_sdk
    import src.core.dashboard as dashboard
    import src.core.db as db
    import src.core.oauth as oauth
    import src.core.roster as roster
    import src.modules.connect.db as connect_db
    import src.modules.connect.jobs as connect_jobs
    import src.modules.connect.slack_api as connect_slack
    import src.modules.connect.zoom as zoom
    import src.modules.insights.db as insights_db
    import src.modules.kudos.db as kudos_db
    import src.modules.standup.handlers as handlers
    import src.modules.standup.workflow as workflow
    from flask import jsonify, request, session
    from src.core.api import csrf_token
    from src.http_app import create_http_app

    state = BrowserData()

    def patch(target, name, value):
        if patcher is None:
            setattr(target, name, value)
        else:
            patcher.setattr(target, name, value)

    def install(target, mapping):
        for name, value in mapping.items():
            patch(target, name, value)

    patch(dashboard, "db", db)
    patch(oauth, "db", db)
    patch(dashboard, "verify_login_token", oauth.verify_login_token)
    install(
        db,
        {
            "get_installation": lambda team: {
                "team_id": team,
                "team_name": state.team_name,
                "bot_token": "fake-browser-token",
            },
            "get_workspace_config": lambda team: deepcopy(state.workspace),
            "upsert_workspace_config": lambda team, **fields: state.workspace.update(fields),
            "get_member_role": lambda team, user: state.roles.get(user, "member"),
            "can_administer": lambda team, user, module=None: (
                state.roles.get(user) == "admin" or (module is not None and module in state.grants.get(user, set()))
            ),
            "module_admin_grants": lambda team, user: state.grants.get(user, set()),
            "team_module_admins": lambda team: deepcopy(state.grants),
            "count_admins": lambda team: sum(role == "admin" for role in state.roles.values()),
            "get_all_members": lambda team: deepcopy(state.members),
            "get_active_members": lambda team: [
                {**deepcopy(m), "role": state.roles[m["user_id"]]} for m in state.members
            ],
            "set_member_role": lambda team, user, role: state.roles.update({user: role}),
            "upsert_member": lambda **fields: None,
            "grant_module_admin": lambda team, user, module, granted_by: state.grants.setdefault(user, set()).add(
                module
            ),
            "revoke_module_admin": lambda team, user, module: state.grants.setdefault(user, set()).discard(module),
            "get_standup_schedules": lambda team: deepcopy(state.schedules),
            "create_standup_schedule": state.create_schedule,
            "update_standup_schedule": lambda team, schedule_id, **fields: state.update(
                state.schedules, schedule_id, **fields
            ),
            "delete_standup_schedule": lambda team, schedule_id: state.delete(state.schedules, schedule_id),
            "get_standups": lambda team, **kwargs: deepcopy(state.responses),
            "export_standups": lambda *args: deepcopy(state.responses),
            "get_participation_overview": lambda team, days=7: state.overview(days),
            "granted_scopes": lambda team: {
                scope
                for spec in __import__("src.modules", fromlist=["REGISTRY"]).REGISTRY
                for scope in spec.required_scopes
            },
            "module_settings": lambda team: deepcopy(state.module_settings),
            "has_scopes": lambda team, scopes: True,
            "set_module_enabled": lambda team, name, enabled: state.module_settings.update({name: enabled}),
            "get_workspace_by_feed_token": lambda token: (
                deepcopy(state.workspace) if token == state.workspace["feed_token"] else None
            ),
            "get_webhooks": lambda team: deepcopy(state.hooks),
            "get_webhook": lambda team, hook_id: deepcopy(next((h for h in state.hooks if h["id"] == hook_id), None)),
            "add_webhook": state.create_hook,
            "update_webhook": state.update_hook,
            "rotate_webhook_secret": lambda team, hook_id, secret: state.update(state.hooks, hook_id, secret=secret),
            "delete_webhook": lambda team, hook_id: state.delete(state.hooks, hook_id),
            "get_webhook_deliveries": lambda *args, **kwargs: [
                {
                    "id": 1,
                    "webhook_id": 1,
                    "event_type": "standup.completed",
                    "status_code": 200,
                    "ok": True,
                    "signed": True,
                    "error": None,
                    "duration_ms": 24,
                    "created_at": state.now,
                }
            ],
            "get_mcp_keys": lambda team: deepcopy(state.keys),
            "generate_mcp_key": state.create_key,
            "revoke_mcp_key": lambda key_id, team: state.update(state.keys, key_id, active=False),
            "suppress_email": lambda email: None,
            "revoke_email_consent": lambda email: None,
            "grant_email_consent": lambda email, **kwargs: None,
        },
    )
    patch(roster, "db", db)
    install(
        connect_db,
        {
            "get_programs": lambda team: deepcopy(state.programs),
            "get_program": lambda program_id: deepcopy(
                next((p for p in state.programs if p["id"] == program_id), None)
            ),
            "create_program": state.create_program,
            "update_program": lambda team, program_id, **fields: state.update(state.programs, program_id, **fields),
            "owns_program": lambda team, program_id: any(
                p["id"] == program_id and p["team_id"] == team for p in state.programs
            ),
            "delete_program": lambda team, program_id: state.delete(state.programs, program_id),
            "optout_user_ids": lambda team, program_id: set(),
            "recent_rounds": lambda team, program_id, *args: deepcopy(state.rounds),
            "round_matches": lambda team, round_id: [
                {
                    "id": 1,
                    "member_ids": ["U_ADMIN", "U_MEMBER"],
                    "met": True,
                    "delivered_at": state.now,
                    "nudged_at": None,
                    "agreed_slot_utc": state.now,
                    "zoom_join_url": None,
                }
            ],
            "member_states": lambda team, program_id: deepcopy(state.member_states),
            "pair_counts": lambda team, program_id: {m["user_id"]: 1 for m in state.members},
            "opt_in": lambda team, program_id, user_id: state.member_states.update(
                {user_id: {"state": "in", "until": None}}
            ),
            "opt_out": lambda team, program_id, user_id, **kwargs: state.member_states.update(
                {user_id: {"state": "out", "until": None}}
            ),
            "snooze": lambda team, program_id, user_id, until: state.member_states.update(
                {user_id: {"state": "snoozed", "until": until}}
            ),
            "personal_state": lambda team, program_id, user_id: deepcopy(
                state.member_states.get(user_id, {"state": "in", "until": None})
            ),
            "participation": lambda team, program_id, rounds: [
                {"user_id": m["user_id"], "paired": 1, "met": 1, "missed": 0, "no_reply": 0, "last_met": state.now}
                for m in state.members
            ],
            "zoom_link_summary": lambda team: {"linked": 2, "needs_reconnect": 0},
        },
    )
    install(
        kudos_db,
        {
            "get_kudos": lambda team, limit: deepcopy(state.kudos[:limit]),
            "get_kudos_leaderboard": lambda team, days: [
                {"to_user": "U_ADMIN", "received": 5, "last_kudos": state.now}
            ],
            "get_giver_leaderboard": lambda team, days: [{"user_id": "U_MEMBER", "given": 5, "last_given": state.now}],
            "get_config": lambda team: deepcopy(state.kudos_config),
            "set_config": lambda team, emoji, allowance: (
                state.kudos_config.update(emoji=emoji, daily_allowance=allowance, token_auto=False)
                or deepcopy(state.kudos_config)
            ),
        },
    )
    install(
        insights_db,
        {
            "unrecognised_contributors": lambda team, **kwargs: [
                {
                    "user_id": "U_LEAD",
                    "real_name": "Sam Rivera",
                    "standups": 12,
                    "last_standup": state.today,
                    "kudos": 0,
                }
            ],
            "blocker_rows": lambda team, **kwargs: {
                "U_ADMIN": [
                    {
                        "user_id": "U_ADMIN",
                        "real_name": "Alex Morgan",
                        "standup_date": state.today - timedelta(days=i),
                        "blockers": "Waiting for design review",
                    }
                    for i in reversed(range(4))
                ]
            },
            "todays_standups": lambda team: deepcopy(state.responses),
            "active_schedules": lambda team: deepcopy(state.schedules),
            "recent_kudos": lambda team, limit: deepcopy(state.kudos[:limit]),
            "connect_program_timing": lambda team: {
                "program_id": 1,
                "name": "Friday coffee",
                "interval_weeks": 1,
                "day_of_week": 4,
                "next_scheduled": state.now + timedelta(days=3),
                "last_round": state.now - timedelta(days=4),
            },
        },
    )
    install(
        workflow,
        {
            "get_rules": lambda team: deepcopy(state.rules),
            "save_rule": lambda **fields: (
                state.rules.append({"id": len(state.rules) + 1, "active": True, "created_at": state.now, **fields})
                or state.rules[-1]["id"]
            ),
            "delete_rule": lambda rule_id, team: state.delete(state.rules, rule_id),
        },
    )
    patch(zoom, "configured", lambda: True)
    patch(connect_jobs, "run_round", lambda *args, **kwargs: None)
    patch(connect_slack, "channel_member_ids", lambda *args: [m["user_id"] for m in state.members])
    patch(
        handlers,
        "deliver_webhook",
        lambda hook, event, payload, **kwargs: {
            "webhook_id": hook["id"],
            "event": event,
            "signed": True,
            "status_code": 200,
            "ok": True,
            "error": None,
            "duration_ms": 24,
        },
    )
    # URL validation is independently unit tested; this adapter accepts only
    # the reserved test host and prevents a DNS lookup in browser tests.
    patch(dashboard, "_is_safe_webhook_url", lambda url: url.startswith("https://hooks.example.test/"))

    class Slack:
        def __init__(self, *args, **kwargs):
            pass

        def users_list(self, **kwargs):
            return {
                "members": [
                    {
                        "id": m["user_id"],
                        "name": m["display_name"],
                        "tz": "UTC",
                        "is_bot": False,
                        "deleted": False,
                        "profile": {
                            "real_name": m["real_name"],
                            "display_name": m["display_name"],
                            "email": m["email"],
                            "image_48": "",
                        },
                    }
                    for m in state.members
                ]
            }

        def users_info(self, user):
            return {"user": next(m for m in self.users_list()["members"] if m["id"] == user)}

        def users_conversations(self, **kwargs):
            return {"channels": deepcopy(state.channels)}

        def conversations_members(self, **kwargs):
            return {"members": [m["user_id"] for m in state.members]}

        def conversations_info(self, channel):
            return {"channel": next(c for c in state.channels if c["id"] == channel)}

    patch(slack_sdk, "WebClient", Slack)
    patch(oauth, "WebClient", Slack)
    patch(zoom, "exchange_code", lambda code: None)
    from src.core import mailer

    patch(mailer, "sync_contact", lambda email: None)
    patch(mailer, "unsync_contact", lambda email: None)
    app = create_http_app(schema_only=True)
    app.config.update(
        TESTING=True, SECRET_KEY="browser-tests-only-not-a-production-secret", SESSION_COOKIE_SECURE=False
    )

    @app.post("/__test__/session")
    def test_session():
        role = request.args.get("role", "admin")
        user_id = {
            "admin": "U_ADMIN",
            "member": "U_MEMBER",
            "feature-admin": "U_LEAD",
            "feature_admin": "U_LEAD",
            "standup-admin": "U_LEAD",
        }.get(role, "U_MEMBER")
        session.clear()
        session.update(team_id=state.team_id, team_name=state.team_name, user_id=user_id)
        return jsonify(role=role, csrf_token=csrf_token())

    @app.post("/__test__/reset")
    def reset():
        state.reset()
        session.clear()
        return jsonify(ok=True)

    @app.get("/__test__/health")
    def health():
        return jsonify(status="ok")

    @app.get("/__test__/login-link")
    def login_link():
        token = oauth._make_login_token(state.team_id, "U_ADMIN")
        return jsonify(url=f"/dashboard?t={token}")

    app.extensions["browser_test_data"] = state
    return app
