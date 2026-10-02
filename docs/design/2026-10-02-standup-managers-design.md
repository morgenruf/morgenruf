# Per-standup managers

Status: approved in chat 2026-10-02.

## Why

A team lead in a CloudDrove workspace could not change his own team's standup.
The only way to let him was the Standups admin grant, which covers every
standup in the workspace: other teams' questions, schedules and members, and
deleting them. In a company with several teams each lead should run their own
standup without holding the keys to everyone else's.

## Roles

| | Workspace admin | Standups admin | Manager of a standup | Member |
|---|---|---|---|---|
| Create a standup | yes | yes | no | no |
| Edit questions, schedule, timezone, participants, reminders | all | all | only theirs | no |
| Pause or resume | all | all | only theirs | no |
| Move to another channel | yes | yes | no | no |
| Delete | yes | yes | no | no |
| Assign managers | yes | yes | no | no |
| Automation rules | yes | yes | no | no |

Deliberate limits:

1. A manager cannot change the channel, so a standup cannot be moved to post
   somewhere the admin did not choose.
2. A manager cannot delete; pausing covers "stop for now" without losing
   history.
3. A manager cannot appoint managers, so access does not spread sideways.

## Data

Migration `068_standup_managers.sql` (067 is taken by celebration banners):

```sql
CREATE TABLE IF NOT EXISTS standup_managers (
    schedule_id INTEGER NOT NULL REFERENCES standup_schedules(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    added_by    TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (schedule_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_standup_managers_user ON standup_managers (team_id, user_id);
```

Deleting a standup removes its managers. Uninstall purges the table with the
other per-team tables. At most 10 managers per standup.

## The rule

`db.can_manage_standup(team_id, user_id, schedule_id) -> bool`: true for a
workspace admin, a Standups admin (`can_administer(team, user, "standup")`), or
a row in `standup_managers` for that schedule in that team.

`db.managed_schedule_ids(team_id, user_id) -> set[int]` for listing.

Every path that edits one standup uses the rule. Creating, deleting, changing
the channel, assigning managers and automation rules keep
`can_administer(..., "standup")`.

## Dashboard API

- `GET /dashboard/api/standups`: each standup gains `can_manage` (bool) and
  `managers` (user ids, shown to anyone who can manage it, empty otherwise).
- `PUT /dashboard/api/standups/<id>`: was Standups admin only; now
  `can_manage_standup`. If the caller is only a manager and the body changes
  `channel_id`, 403 "Only standup admins can move a standup to another
  channel."
- `DELETE /dashboard/api/standups/<id>`: unchanged, Standups admin.
- `PUT /dashboard/api/standups/<id>/managers` (new, Standups admin): body
  `{"user_ids": [...]}`, replaces the list. Returns the list. Each newly added
  person gets a DM.

## Slack

- App Home normal view: the Configure button shows on a standup when the
  person can manage it (today: only when they are a Standups admin).
- A manager who is not a participant sees the standups they manage under
  "Standups you manage", each with Configure.
- `edit_standup`, `standup_overflow` (pause, resume, edit) and the
  `create_standup_modal` submission check `can_manage_standup` for the
  standup in question. Delete in the overflow stays admin-only and is not
  offered to managers.
- The edit modal shows the channel as text, not a picker, to a manager. The
  submission rejects a channel change from a manager in any case.
- Creating (`open_create_standup`, quick start) stays admin-only.
- A member who can manage nothing sees, under their standups: "Need to change
  a standup? Ask <@installer> to make you its manager."
- On being added as a manager: DM "You now manage *<name>* in <#channel>.
  Change it from App Home or the dashboard."

## Frontend

- Standups page: Edit shows where `can_manage`; Delete only for admins.
- Edit dialog: a Managers people picker, for Standups admins only. The channel
  select is disabled for managers with a short note.

## Not changing

Slack scopes, commands and event subscriptions (Marketplace review), API keys,
MCP, the Standups admin grant.

## Tests

- `can_manage_standup` for each role, and across teams (a manager row in
  another team never counts).
- Each dashboard route and each Slack action as: workspace admin, Standups
  admin, manager of this standup, manager of another standup, member.
- Manager channel change refused (API and modal). Manager delete refused.
- Managers endpoint: admin only, replaces the list, DMs only new managers,
  limit enforced, unknown standup 404.
- App Home: Configure per standup, "Standups you manage", the hint.
- Frontend: Edit and Delete visibility, channel locked for managers, Managers
  picker for admins.
