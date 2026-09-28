# Design: Onboarding buddies (sub-project 4)

Date: 2026-09-27
Status: Draft for review. Decisions the owner still has to make are in
section 14, each with a recommendation.
Scope: a new hire is matched with an experienced teammate as their buddy,
and both get a short checklist over the first weeks with gentle nudges.
GitHub issue #179. Replaces "Onboarding journeys" in `ROADMAP.md`.
Depends on: Member profile (#176, `2026-09-27-profile-and-celebrations-design.md`)
and Intros (#177, `2026-09-27-intros-design.md`), which adds the `team_join`
listener, the new hire classifier and `members.is_guest`.

## 1. Why, and what this is not

A buddy is the person a new hire can ask the small questions they would not
ask their manager. Donut sells this inside Journeys, now AI-driven and wired
to HRIS and ATS systems. That is the enterprise version Morgenruf does not
want to be (`2026-09-16-connect-roadmap.md`, Position).

Morgenruf's version is deliberately small:

- one buddy per new hire, picked from volunteers;
- a checklist of a handful of items with day offsets, written by HR once;
- one DM per person per day at most, and only on days something is due;
- everything scheduled lives in the database.

Out of scope: HRIS or ATS sync, pre-boarding before the person has a Slack
account, AI-written plans, multi-track journeys per department, surveys
beyond one closing question, manager dashboards.

## 2. Current state (verified 2026-09-27 against `origin/main`, 1.8.13)

| Fact | Where |
|---|---|
| `match()` groups an undifferentiated pool; it has no notion of one side being fixed | `connect/matcher.py:55-193` |
| Pair cost is history plus a recency penalty; never-paired costs zero | `matcher.py:33-41` |
| Working-hours reachability is `hours.can_meet(tz_a, tz_b, minimum_hours)` | `connect/hours.py:67-69`, used by `matcher.py:49-52` |
| Seeded, sorted-then-shuffled ordering, so a retry gives the same answer | `matcher.py:97-101` |
| Connect's pool is "members of a channel", read with `channel_member_ids` | `connect/jobs.py:113-121`, `connect/slack_api.py` |
| `eligible_members` is active and not on vacation | `core/roster.py:36-59` |
| Group DMs are opened with `conversations.open`; same people give the same channel | `connect/slack_api.py:73-80` |
| One round per programme per day, enforced with an advisory lock plus a conditional insert | `connect/db.py:310-339` |
| Connect's nudge and close are in-memory `DateTrigger` jobs, lost on restart and, reading `reconcile_jobs`, likely removed by the next two-minute module job sync | `connect/jobs.py:347-368`, `core/scheduler.py:1775-1792` |
| Module jobs are reconciled by id only, so a trigger built from a setting does not move when the setting changes | `scheduler.py:1783-1791` |
| `/morgenruf` exists and is handled by standup as help | `slack-manifest.yaml:16`, `standup/handlers.py:1510-1511`; the profile release turns it into a subcommand router |
| `mpim:write` and `im:write` are already requested at install | `core/scopes.py:16-34` |

## 3. How it works, end to end

```
new hire joins ──► core team_join listener (Intros release) ──► kind == "new"
                                                      │
               Buddies.on_member_joined: create pairing (state = matching)
                                                      │
   every 15 min sweep: match pending pairings ──► pick buddy ──► introduce
                                                      │
                     create buddy_tasks rows from the template (due dates)
                                                      │
   same sweep: send tasks due today, in each recipient's morning ──► mark sent
                                                      │
            last item done or day 30 passed ──► closing question ──► ended
```

A pairing can also be created by hand: from the dashboard or with
`/morgenruf buddy @hire` (section 9), for someone who joined before Buddies
was enabled or whom the classifier did not treat as new.

## 4. Who can be a buddy

A candidate must pass every hard rule:

| Rule | Default | Source |
|---|---|---|
| In the buddy pool channel | `#buddies`, chosen by HR | `channel_member_ids`, as Connect does |
| Active and not on vacation | | `roster.eligible_members` |
| Not a guest | | `members.is_guest` (Intros release) |
| Not the hire, and not the hire's manager if one is set | | pairing row |
| Tenure at least N days | 90 | profile `start_date`; if missing, `members.created_at` as a lower bound |
| Fewer than M active buddyships | 1 | `buddy_pairings` |
| Not currently a new hire in an active pairing themselves | | `buddy_pairings` |

**Opt-in through a channel.** Joining the pool channel is volunteering;
leaving it is stepping down. This is the same model as Connect (a coffee
chat programme is a channel), needs no new opt-in UI, and makes the pool
visible: HR can see who volunteered by opening the channel. See open
question 1 for the alternative (everyone with tenure, opt-out).

**Tenure without a start date.** Many members will have no `start_date`.
`members.created_at` is when Morgenruf first saw them, which is never later
than when they joined, so it is a safe lower bound: if Morgenruf has known
someone for 90 days, they have been there at least 90 days. A veteran in a
workspace that installed Morgenruf last month does not qualify until HR
imports start dates (the profile CSV import) or the veteran fills in their
own. The settings page shows "12 volunteers, 7 eligible, 5 missing a start
date" so HR knows why.

**Load.** At most one active buddyship per buddy by default, so a small pool
is not burned out by a hiring wave. After a buddyship ends, a 30 day
cooldown is a soft preference, not a hard rule (section 5).

## 5. Matching

### The fixed-role constraint

`match()` takes one pool and groups it. Buddies has two roles: one fixed
anchor (the hire) and a candidate list (eligible buddies), and exactly one
candidate is chosen. `match()` cannot express that, and bending it to would
put coffee chats at risk.

So `matcher.py` gains one new pure function alongside `match()`, which is
left untouched:

```python
def pick_partner(
    anchor: str,
    candidates: list[str],
    history: dict[tuple[str, str], PairStat],
    seed: int,
    timezones: dict[str, str] | None = None,
    minimum_overlap_hours: float = 0.0,
    extra_cost: Callable[[str], int] | None = None,
) -> str | None:
    """The single best candidate for `anchor`, or None when there is none."""
```

It reuses what Connect already proved:

- `_cost` over `history`, so if a hire's first buddy is swapped out, the
  replacement is someone else;
- `_can_meet` / `hours.can_meet` for working-hours overlap;
- sort, then seeded shuffle (`matcher.py:97-101`), so a retried sweep picks
  the same buddy and a test can assert on it.

For a brand new hire, pair history is empty by definition, so most of the
ranking comes from `extra_cost`, which Buddies supplies:

| Term | Cost | Why |
|---|---|---|
| No working-hours overlap of 1 hour with the hire | +50 | Strong preference, not a hard rule: an async buddy beats none |
| Different `location` (case-insensitive, trimmed) | +10 | Someone who can show them the office, or at least the city |
| Buddied someone in the last 30 days | +20 | Spread the work across volunteers |
| Each active buddyship already held (when M > 1) | +15 | Same |
| Same `role`, when HR turned on "prefer same role" | -5 | Off by default; role is free text and matching it is weak |

Lowest total wins; ties fall to the seeded order. `minimum_overlap_hours`
stays 0 for Buddies (the overlap is scored, not filtered), which is also
what keeps `pick_partner` from ever returning None while a candidate exists.

### Concurrency

Two hires matched in the same sweep, or on two pods during a rolling update,
could both pick the same buddy and break the load limit. Matching takes
`pg_advisory_xact_lock(hashtext('buddy_match'), hashtext(team_id))` for the
workspace, counts loads inside the transaction, and writes the chosen buddy
before releasing it, the same pattern as `create_round`
(`connect/db.py:337`). Hires are matched oldest first.

### Nobody eligible

The pairing stays in `matching`, and each module admin (or workspace admin
if there are none) gets one DM, once per pairing (section 10). The sweep
retries every run, so a volunteer joining the channel resolves it without
anyone pressing anything. After 7 days unmatched, the pairing is `expired`
and no checklist is sent.

### Why this does not break coffee chats

- `match()` and every existing test for it are unchanged; `pick_partner` is
  added beside it.
- No Connect table is read or written. Buddies history is its own table.
- Buddies imports `connect.matcher` and `connect.hours`, which are pure and
  do no I/O, so disabling Connect in a workspace does not affect Buddies.
  Whether those two files move to core instead is open question 5.

## 6. What HR configures

Buddies is `delegable=True`, so a workspace admin can make the HR person a
Buddies admin (`module_admins`) without the rest of the workspace.

### Settings

| Setting | Default |
|---|---|
| Buddy pool channel | none, required to enable |
| Minimum tenure | 90 days |
| Buddyships at a time per buddy | 1 |
| Assign automatically when someone new joins | on |
| Include the manager | off |
| Prefer same role | off |
| Programme length | 30 days (the last day any item can fall on) |

### Checklist template

A list of items, each with:

- **day**: offset from the hire's start (day 0 is the first day);
- **for**: hire, buddy, both, or manager;
- **text**: up to 300 characters, Slack mrkdwn.

Editable on the dashboard (add, edit, reorder, delete, "restore defaults").
Items for the manager are ignored for pairings without one.

Default template, shipped so the module works on day one:

| Day | For | Text |
|---|---|---|
| 0 | both | Say hello and find 30 minutes this week for a coffee. ☕ |
| 1 | hire | Ask your buddy which channels are worth joining, and which you can mute. |
| 3 | buddy | Check in: how is the setup going? A two-line message is enough. |
| 5 | hire | What's one thing that confused you this week? Ask your buddy. There are no silly questions. |
| 10 | both | Grab lunch or a virtual coffee. No agenda needed. |
| 20 | buddy | Introduce your new teammate to one person from another team. |
| 30 | both | Last one: a quick chat about how the first month went. |

### Day offsets, working days and holidays

Due date is start date plus the offset in calendar days, in the hire's own
timezone. A due date on a non-working day (outside the workspace's working
days, or on a holiday in the core workspace calendar HR keeps) moves to the
next working day. See decision 4.

Each task is sent at 10:00 in the recipient's own timezone (`members.tz`),
so a buddy in another zone is not nudged at night. There is no Buddies
timezone setting.

## 7. Data

Migration `NNN_buddies.sql` in `app/src/modules/buddies/migrations`, next
free number at implementation time. Every table references
`installations(team_id) ON DELETE CASCADE`, so uninstall cleans up and
rollback stays a plain image revert.

```sql
CREATE TABLE IF NOT EXISTS buddy_settings (
    team_id          TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    pool_channel_id  TEXT,
    min_tenure_days  SMALLINT NOT NULL DEFAULT 90,
    max_active       SMALLINT NOT NULL DEFAULT 1 CHECK (max_active BETWEEN 1 AND 5),
    auto_assign      BOOLEAN NOT NULL DEFAULT TRUE,
    include_manager  BOOLEAN NOT NULL DEFAULT FALSE,
    prefer_same_role BOOLEAN NOT NULL DEFAULT FALSE,
    length_days      SMALLINT NOT NULL DEFAULT 30 CHECK (length_days BETWEEN 7 AND 120),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS buddy_template_items (
    id          SERIAL PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    day_offset  SMALLINT NOT NULL CHECK (day_offset BETWEEN 0 AND 120),
    audience    TEXT NOT NULL CHECK (audience IN ('hire', 'buddy', 'both', 'manager')),
    body        TEXT NOT NULL,
    position    SMALLINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS buddy_pairings (
    id             SERIAL PRIMARY KEY,
    team_id        TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    hire_id        TEXT NOT NULL,
    buddy_id       TEXT,
    manager_id     TEXT,
    start_date     DATE NOT NULL,
    state          TEXT NOT NULL DEFAULT 'matching'
                   CHECK (state IN ('matching', 'active', 'ended', 'cancelled', 'expired')),
    source         TEXT NOT NULL CHECK (source IN ('join', 'dashboard', 'command')),
    created_by     TEXT,
    mpim_channel_id TEXT,
    introduced_at  TIMESTAMPTZ,
    admins_told_at TIMESTAMPTZ,
    feedback       TEXT CHECK (feedback IN ('very', 'somewhat', 'not_really')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at       TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS buddy_one_open_pairing_per_hire
    ON buddy_pairings (team_id, hire_id) WHERE state IN ('matching', 'active');

CREATE TABLE IF NOT EXISTS buddy_tasks (
    id          SERIAL PRIMARY KEY,
    pairing_id  INT NOT NULL REFERENCES buddy_pairings(id) ON DELETE CASCADE,
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    item_id     INT,
    recipient   TEXT NOT NULL,
    audience    TEXT NOT NULL,
    body        TEXT NOT NULL,
    due_date    DATE NOT NULL,
    state       TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'sending', 'sent', 'skipped', 'cancelled')),
    sent_at     TIMESTAMPTZ,
    done_at     TIMESTAMPTZ,
    UNIQUE (pairing_id, item_id, recipient)
);
CREATE INDEX IF NOT EXISTS idx_buddy_tasks_due
    ON buddy_tasks (team_id, due_date) WHERE state = 'pending';
```

Notes:

- **Tasks are rows, created when the pairing becomes active**, one per
  recipient per item, with the text copied from the template. Editing the
  template later changes future pairings, not ones in flight. This is the
  "nudges persisted in the database, not memory" requirement: a restart, a
  second pod, or the reconciler removing a job cannot lose a nudge, because
  there is nothing to lose outside the table.
- **The partial unique index** means one open pairing per hire, whatever
  creates it: a duplicate `team_join`, a second pod, an admin clicking twice.
- **`UNIQUE (pairing_id, item_id, recipient)`** makes task creation safe to
  retry.
- `buddy_pairings` is also Buddies' pair history for `pick_partner` and the
  cooldown. Ended pairings older than 12 months are deleted by the sweep, and
  a hire's or buddy's rows go with the profile under its 30 day leaver rule.

## 8. The sweep

`plan_jobs` returns one job per workspace with Buddies active:

```python
JobSpec(key="sweep", trigger=IntervalTrigger(minutes=15), func=sweep, args=(team_id, bot_token))
```

Interval, not cron, for the same reason as Intros: `reconcile_jobs` compares
ids only, and send times are per recipient anyway. The job id is in
`plan_jobs`, so the reconciler keeps it.

Each run, in order, each step in its own transaction and its own try, so a
failure in one step or one pairing does not stop the rest:

1. **Match** pairings in `matching`, oldest first, under the workspace lock
   (section 5). On success: set `buddy_id`, `state = 'active'`, create the
   tasks, open the group DM, post the introduction, set `introduced_at` and
   `mpim_channel_id`. The introduction is sent only if `introduced_at` is
   null, and `introduced_at` is set immediately after the post, so a retry
   after a crash between the two re-sends at most one message.
2. **Tell admins** once about pairings still in `matching` after one sweep
   (`admins_told_at`), and expire ones older than 7 days.
3. **Watch for leavers.** Hire inactive: pairing `cancelled`, pending tasks
   `cancelled`. Buddy inactive or out of the pool channel: pairing back to
   `matching` with the old buddy in its history, tell the hire (section 10).
4. **Send due tasks.** For each pending task whose `due_date` is today or
   earlier in the recipient's timezone and whose recipient's local time is
   past 10:00, claim with `UPDATE ... SET state = 'sending' ... FOR UPDATE
   SKIP LOCKED RETURNING`, group by recipient, send one DM per recipient,
   mark `sent`. Tasks more than 3 days overdue (the bot was down) are
   `skipped` rather than sent: a week-old "say hello" is noise.
5. **End** active pairings past `start_date + length_days`: send the closing
   question to the hire and the thank-you to the buddy, `state = 'ended'`.

A task stuck in `sending` after a crash is not retried, the same at-most-once
choice Intros makes; `/morgenruf buddy` still lists it, so nothing is lost
from the checklist.

## 9. `/morgenruf buddy`

A subcommand on the `/morgenruf` router the profile release introduces. No
manifest change.

| Command | Who | Does |
|---|---|---|
| `/morgenruf buddy` | anyone | Ephemeral: your current buddy or buddies, and your checklist with Done buttons. Nobody: how to volunteer ("join #buddies") |
| `/morgenruf buddy @hire` | workspace or Buddies admin | Create a pairing for that person now and match automatically |
| `/morgenruf buddy @hire @buddy` | workspace or Buddies admin | Same, with that buddy. Skips the pool, tenure and load rules, since HR chose deliberately; still refuses a guest, a bot, or the hire themselves |
| `/morgenruf buddy end @hire` | workspace or Buddies admin | End the pairing early, no closing question |

Non-admins using an admin form get: "Only a Buddies admin can assign buddies.
Ask one of: @Ana, @Tom."

The App Home gets a short Buddies section through `home_blocks` while a
pairing is active, showing the other person and the next item.

### Dashboard

A Buddies page for workspace and Buddies admins: settings, the template
editor, and a pairings list (hire, buddy, start, progress as "4 of 9 done",
state) with Reassign, End and "Pick someone" for unmatched hires. A plain
member sees nothing here; their view is `/morgenruf buddy` and App Home.

## 10. Messages

Warm, short, Donut style, the same voice as Intros and Celebrations. Names
are mentions. No pronouns.

### Introduction (group DM: hire, buddy, and manager when included)

```
👋 @Priya, meet @Tom, your onboarding buddy!

Tom has been at Acme for 3 years and is in Berlin too.
Over the next month I'll drop a few small things for you two to do.

First one: find 30 minutes this week for a coffee and a hello. ☕
```

The second line uses what exists: tenure only from a real `start_date`
("has been at Acme for a while" from `created_at` would be a guess, so it
is left out), "is in Berlin too" only on a location match, "works as
Support Engineer" when there is a role and no location match. With nothing,
the line is "Tom has offered to help you find your feet."

When the manager is included, a third line: "@Mara, you're here so you know
who Priya's buddy is. Nothing for you to do."

### Heads-up DM to the buddy, sent with the introduction

```
🙌 You're @Priya's onboarding buddy!

Priya started today as Product Designer. Thanks for volunteering.
I'll send you a short nudge on the days something is due. That's it.

[ Show the checklist ]
```

### Daily nudge (one per recipient per day, only when something is due)

```
📋 Day 5 with @Tom

What's one thing that confused you this week? Ask your buddy.
There are no silly questions.

[ Done ]   [ Show my checklist ]
```

```
📋 Day 3 with @Priya

Check in: how is the setup going? A two-line message is enough.

[ Done ]
```

Two items due for the same person on the same day are listed in one message,
each with its own Done button.

### Buddy stepped away

To the hire, in the same group DM:

```
🔄 Change of plan: Tom can't be your buddy any more.
I'm finding you someone new and will introduce you shortly.
```

### Nobody to match (to Buddies admins, once per hire)

```
🤔 I couldn't find a buddy for @Priya yet.

Nobody in #buddies has been here 90 days and has room right now.
I'll keep trying. You can also pick someone.

[ Pick someone ]   [ Open Buddies settings ]
```

### End of the programme

To the hire:

```
🎓 That's your first month, Priya!

How helpful was having a buddy?
[ Very ]   [ Somewhat ]   [ Not really ]
```

To the buddy:

```
💛 Thanks for being @Priya's buddy, Tom.
You made someone's first month a lot easier.
```

Answers are stored in `buddy_pairings.feedback` and shown as a count on the
dashboard; that is the only metric Buddies reports.

## 11. Module

```python
MODULE = ModuleSpec(
    name="buddies",
    required_scopes=("users:read", "im:write", "mpim:write"),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,    # buttons, /morgenruf buddy
    register_routes=register_routes,     # settings, template, pairings
    plan_jobs=plan_jobs,                 # the sweep
    claim_dm=None,
    purge=purge,
    nav=(NavItem(label="Buddies", path="#buddies"),),
    default_enabled=False,
    delegable=True,
    home_blocks=home_blocks,
    on_member_joined=on_member_joined,   # contract field added by Intros
)
```

All three scopes are already requested at install (`scopes.py`), so enabling
Buddies needs no reinstall for a workspace that already has coffee chats.
An older install without the mpim scopes stays dark, as Connect does.

`on_member_joined` only acts on `kind == "new"` with `auto_assign` on. It
inserts the pairing with `start_date` = today in the hire's timezone and
`ON CONFLICT DO NOTHING` on the partial index. Matching waits for the next
sweep, at most 15 minutes, so the Intros card and the buddy introduction do
not land in the same minute.

## 12. Tests

Matcher (pure, no database):

- `pick_partner` with an empty pool returns None; with one candidate returns
  it; is deterministic for a seed and independent of input order.
- Overlap is scored, not filtered: a far-timezone candidate is picked only
  when nobody else is left.
- Location match, cooldown, load and same-role terms each change the pick in
  the expected direction.
- History: a swapped-out buddy is not picked again while others exist.
- **Every existing `match()` test passes unchanged**, which is the guarantee
  coffee chats are unaffected.

Eligibility:

- Tenure from `start_date`; from `created_at` when no start date; a guest, a
  person on vacation, an inactive member, the hire, the manager, and a buddy
  at their load limit are all excluded; leaving the pool channel excludes.

Persistence and idempotency (real Postgres):

- Duplicate `team_join` creates one pairing.
- Two concurrent sweeps: one match per hire, load limit held.
- Tasks created once per pairing, correct due dates, non-working day and holiday moved to the next working day,
  per-recipient 10:00 in their own timezone.
- A restart between claim and send does not double-send; a sweep after
  3 days of downtime skips stale tasks and sends current ones.
- Editing the template does not change tasks of an active pairing.
- Hire leaves: tasks cancelled. Buddy leaves: pairing back to matching, old
  buddy not re-picked.
- Nobody eligible: admins told once, expired after 7 days.

Slack surfaces:

- `/morgenruf buddy` for a hire, a buddy, and someone with neither.
- Admin forms refused for a member; explicit buddy skips pool and tenure but
  refuses a guest.
- Message builders: introduction with and without start date, location and
  manager; grouped nudge; no pronouns in any template (a test that scans the
  rendered strings for he, she, him, her, his, hers, they, them, their).

## 13. Deliverables (release 4)

| Surface | Change |
|---|---|
| App | `pick_partner` in `connect/matcher.py`; `modules/buddies` (migration, settings, template editor with defaults, pairings page, sweep, `on_member_joined`, `/morgenruf buddy`, App Home section, messages, feedback) |
| Docs | README (Buddies section, Coming table updated), CHANGELOG, docs.morgenruf.dev Buddies page (setting up the pool channel, tenure and start dates, writing the checklist, what each person receives and when) |
| Website | `/buddies` product page, Donut alternative and compare pages (onboarding row: "buddies and a checklist, no HRIS"), homepage roadmap, `llms.txt` and `llms-full.txt` |

The website deploys only through the Netlify CLI; merging to main does not
deploy it. The release adds no scope and no event subscription, so the
Slack app config does not change.

## 14. Decisions (resolved 2026-09-27)

The owner accepted recommendations 1, 2, 3, 5, 6 and 7, and changed 4:

1. **Pool:** opt-in through a channel. Settings show the eligible count.
2. **Decline:** no "Swap me out" button in v1; HR reassigns.
3. **Manager:** off by default, set per pairing by HR.
4. **Working days and holidays: reused, not ignored.** HR should keep one
   company calendar, not two. To avoid one module reading another's
   settings, working days and the holiday list live in **core** as a
   workspace calendar (built in the Celebrations release, edited from the
   Celebrations settings page for now). Buddies reads the core calendar: a
   checklist task due on a non-working day moves to the **next** working day
   (Celebrations moves to the previous one, since a birthday greeting must
   not be late, while a task should not be early).
5. **Matcher:** imported from Connect in v1; moved to core only when a
   third module needs it.
6. **Tenure:** 90 days, editable.
7. **Length:** 30 days by default, editable up to 120, closing question on
   the last day.
