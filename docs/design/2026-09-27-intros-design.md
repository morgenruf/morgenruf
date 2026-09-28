# Design: Intros (sub-project 3)

Date: 2026-09-27
Status: Draft for review. Decisions the owner still has to make are in
section 13, each with a recommendation.
Scope: a welcome card in a chosen channel when someone joins the workspace,
built from the member profile, and a prompt asking the new joiner to fill
that profile in. GitHub issue #177.
Depends on: Member profile (#176,
`2026-09-27-profile-and-celebrations-design.md`, sections 3 to 6).

## 1. Why

The team finds out someone joined when that person first speaks. By then the
awkward part (nobody knows who they are or what to ask them) has already
happened. Donut's Intros pillar fixes this with a card in a channel.

Morgenruf now has the data a card needs. The member profile (release 1)
stores `role`, `location` and `ask_me_about` in `member_profiles`, a table
the Slack sync can never overwrite. Intros is the first module that reads it
for someone other than the owner.

Intros is also the release that introduces the `team_join` listener. The
Onboarding buddies design (`2026-09-27-onboarding-buddies-design.md`) needs
the same "a new person arrived" signal, so this document puts the listener
and the new hire test in core rather than in the Intros module.

## 2. Current state (verified 2026-09-27 against `origin/main`, 1.8.13)

| Fact | Where |
|---|---|
| No `team_join` handler anywhere | `git grep team_join` is empty |
| Subscribed bot events: `message.im`, `app_mention`, `app_home_opened`, `member_joined_channel` | `slack-manifest.yaml:57-61`, `slack-manifest.json` |
| `users:read` is already requested at install | `app/src/core/scopes.py:28` |
| The two manifests are tested against `scopes.py` and each other | `app/tests/test_oauth_scope_drift.py:37-45` |
| `app/slack-manifest.yaml` and `app/slack-manifest.json` are stale copies (no `/morgenruf`, no mpim scopes, no `member_joined_channel`, last touched in the first Block Kit commits) and no test reads them | `git log app/slack-manifest.yaml` |
| `is_human` drops bots, Slackbot and deleted accounts, but not guests | `app/src/core/slack_users.py:24-30` |
| The roster records no guest flag; Connect dropped `include_guests` for exactly this reason | `connect/migrations/046_drop_include_guests.sql` |
| A `members` row is only created on first contact (channel join, schedule listing, six-hourly sync), with `created_at DEFAULT NOW()` | `001_initial.sql:29-39`, `scheduler.py:1508-1611` |
| Standup's `member_joined_channel` handler DMs "Welcome to the team!" to anyone joining a standup channel | `modules/standup/handlers.py:1349-1382` |
| Bolt fires every matching listener, which is why core owns the single `message` listener and offers it to modules | `main.py:123-151` |
| Module jobs are reconciled every 2 minutes by id only; a changed trigger on an existing id is not replaced | `scheduler.py:1775-1792`, `_SYNC_INTERVAL_MINUTES = 2` at `scheduler.py:1306` |
| Posting needs the bot in the channel: there is no `chat:write.public` | `scopes.py:16-34` |
| `workspace_modules.settings` JSONB exists and nothing reads it | `030_workspace_modules.sql`, `db.py:1817` |

### A known risk this design must not repeat

Connect queues its day three nudge and day six close as in-memory
`DateTrigger` jobs (`connect/jobs.py:347-368`). APScheduler here has an
in-memory job store, so a pod restart loses them.

Reading the code for this design turned up a second way they are lost:
their ids (`connect:{team}:nudge:{round}`) contain colons, and
`reconcile_jobs` removes every live job with a colon in its id that no
module's `plan_jobs` asked for (`scheduler.py:1783-1788`). `plan_jobs` for
Connect only returns `round:{id}` jobs, so the follow-ups look to be removed
by the next module job sync, about two minutes after they are queued. This
has not been reproduced yet; it should be checked with a test before either
new module ships, and tracked as its own Connect bug.

Rule for Intros and Buddies: **anything that must happen later is a row in
the database with a due time, and a periodic sweep planned through
`plan_jobs` sends what is due.** No `DateTrigger`, no job whose id is not in
`plan_jobs`.

## 3. How it works, end to end

```
team_join (Slack) ──► core listener ──► classify: new hire? guest? bot? returning?
                                             │
                          new hire ──────────┤
                                             ▼
                        upsert members row, then offer to active modules
                                             │
                       Intros: insert intro_welcomes row (pending, post_after)
                               DM the new joiner: fill in your profile
                                             │
         every 10 min, per workspace: sweep due rows in posting hours
                                             │
                    claim row ──► post card ──► record ts (posted)
```

## 4. `team_join` subscription

### Manifest change

Add `team_join` to `settings.event_subscriptions.bot_events` in the root
`slack-manifest.yaml` and `slack-manifest.json` (the pair the drift tests
read). `team_join` is delivered with the `users:read` scope, which every
install already holds (`scopes.py:28`).

Extend `test_subscribed_events_have_the_scope_that_delivers_them`
(`test_oauth_scope_drift.py:66-74`) with `"team_join": "users:read"`, and
update the `users:read` description in `scopes.py` to mention it.

The stale `app/slack-manifest.yaml` and `app/slack-manifest.json` should not
get a partial edit. See open question 1.

### Reinstall implications

- **No new scope, so no reinstall.** Slack asks a workspace to reinstall when
  the scope list grows. Adding an event whose scope is already granted is an
  app configuration change: once the hosted app's config lists `team_join`,
  Slack starts delivering it to every existing install. This must be checked
  on the staging app before release (add the event, join a test account,
  confirm the event arrives without reinstalling), because the whole
  rollout plan rests on it.
- **Hosted app:** the owner updates the app config once on api.slack.com
  (paste the manifest). No customer action.
- **Self-hosters:** they own their Slack app, so they must add the event to
  it. The upgrade note in CHANGELOG and the docs page say so in one line.
  Until they do, Intros is enabled and simply never hears of anyone joining.
  The Intros settings page says "Last join seen: never" so this is visible.
- **The module gate:** `required_scopes=("users:read",)`. `is_active`
  (`modules.py:59-72`) then keeps Intros dark for any install that somehow
  lacks it, the same way Connect waits for mpim scopes.
- **No bot reaction on the card.** Adding a 👋 reaction as the bot needs
  `reactions:write`, which is a new scope and therefore a reinstall for
  every workspace. See open question 4 (the Celebrations design has the
  same dependency for its 🎉 reaction).

## 5. Core: one listener, one classifier

### Listener

Core registers the only `team_join` listener, next to `register_dm_listener`
in `main.py`, for the same reason core owns the `message` listener: two
modules each registering `team_join` would each classify, each write the
`members` row, and each talk to the new person.

The module contract gains one defaulted field, like `home_blocks` and
`mcp_tools` did:

```python
# app/src/core/modules.py
on_member_joined: Optional[Callable] = None   # (team_id, user, kind) -> None
```

The listener resolves active modules exactly as the DM listener does
(`main.py:141-150`) and calls each one's `on_member_joined` in registry
order, catching and logging per module so one failure cannot cost the others
their turn. Intros (this release) and Buddies (release 4) implement it.

### Classifier

`app/src/core/newcomers.py`, a pure function over the Slack user object from
the event, the stored `members` row (if any) and the profile (if any):

```python
def classify(user: dict, stored: dict | None, profile: dict | None,
             workspace_team_id: str, now: datetime) -> str:
    """One of: new, guest, bot, external, returning."""
```

Rules, checked in order:

| Kind | Test | Why |
|---|---|---|
| `bot` | `not is_human(user)` or `user.is_app_user` | Reuses `slack_users.is_human`, which already covers bots, Slackbot and deleted accounts |
| `external` | `user.team_id` differs from the workspace | Defensive; Slack Connect people are not workspace members |
| `guest` | `user.is_restricted` or `user.is_ultra_restricted` | Multi-channel and single-channel guests: contractors, agencies, clients |
| `returning` | a `members` row exists with `created_at` more than 24 hours ago | Morgenruf knew this person before, so it is a reactivation or a re-add |
| `returning` | profile `start_date` more than 60 days ago | HR recorded an old start date, for example a move between Enterprise Grid workspaces |
| `new` | everything else | |

Reactivating a deactivated account normally arrives from Slack as
`user_change`, not `team_join`, and Morgenruf does not subscribe to
`user_change`. The design does not rely on that: the `members` row check
catches a reactivation that does arrive as `team_join`, because the six
hourly sync (`scheduler.py:1607-1611`) never deletes rows.

What the classifier cannot know: on Enterprise Grid, someone added to one
more workspace in the org fires `team_join` there too. Without a start date
on file they look new. The "Don't introduce me" button and the admin
"Skip" (section 8) are the safety valves; see open question 3.

### Also in core, for every kind except `bot` and `external`

- `db.upsert_member(team_id, user_id, **member_profile(user))`, so the new
  person is on the roster immediately instead of up to six hours later.
- A new `members.is_guest BOOLEAN NOT NULL DEFAULT FALSE` column, written
  here and by the six-hourly sync from `is_restricted or
  is_ultra_restricted`. It is Slack-owned data, so the sync owning it is
  right. Buddies needs it for eligibility, and it is what Connect's
  `include_guests` was waiting for (`046_drop_include_guests.sql`).

## 6. Intros module

`app/src/modules/intros/`, registered in `src/modules/__init__.py` after
Connect:

```python
MODULE = ModuleSpec(
    name="intros",
    required_scopes=("users:read",),
    migrations_dir=Path(__file__).parent / "migrations",
    register_slack=register_handlers,    # buttons on the DM and the card
    register_routes=register_routes,     # settings page, pending list
    plan_jobs=plan_jobs,                 # the sweep
    claim_dm=None,
    purge=purge,
    nav=(NavItem(label="Intros", path="#intros"),),
    default_enabled=False,
    delegable=True,                      # HR can run it without workspace admin
    on_member_joined=on_member_joined,
)
```

Layout mirrors `kudos` (`modules/kudos/__init__.py`): `handlers.py`,
`dashboard.py`, `jobs.py`, `db.py`, `blocks.py`, `schemas.py`, `migrations/`.

### Data

Migration `NNN_intros.sql` in the module's `migrations/` (next free number at
implementation time; 052 if Intros ships straight after the profile).

```sql
CREATE TABLE IF NOT EXISTS intro_settings (
    team_id        TEXT PRIMARY KEY REFERENCES installations(team_id) ON DELETE CASCADE,
    channel_id     TEXT,
    delay_hours    SMALLINT NOT NULL DEFAULT 24 CHECK (delay_hours BETWEEN 0 AND 168),
    timezone       TEXT NOT NULL DEFAULT 'UTC',
    post_from      SMALLINT NOT NULL DEFAULT 9  CHECK (post_from BETWEEN 0 AND 23),
    post_until     SMALLINT NOT NULL DEFAULT 17 CHECK (post_until BETWEEN 1 AND 24),
    working_days   SMALLINT[] NOT NULL DEFAULT '{0,1,2,3,4}',
    welcome_guests BOOLEAN NOT NULL DEFAULT FALSE,
    ask_profile    BOOLEAN NOT NULL DEFAULT TRUE,
    last_join_at   TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intro_welcomes (
    team_id     TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    post_after  TIMESTAMPTZ NOT NULL,
    state       TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'posting', 'posted', 'skipped', 'cancelled')),
    reason      TEXT,
    channel_id  TEXT,
    message_ts  TEXT,
    dm_ts       TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_intro_welcomes_due
    ON intro_welcomes (team_id, post_after) WHERE state = 'pending';
```

Settings get their own table rather than `workspace_modules.settings`, which
nothing reads today and has no typed columns; Connect and Kudos both keep
their config in module tables too.

`PRIMARY KEY (team_id, user_id)` is the idempotency guarantee: one welcome
per person per workspace, ever. A second `team_join` for the same person (a
Slack retry, a second pod, a genuine re-add) hits `ON CONFLICT DO NOTHING`.

### `on_member_joined`

1. Record `last_join_at` (for the "Last join seen" line).
2. `kind == "new"`, or `kind == "guest"` with `welcome_guests` on: insert
   the row with `post_after = joined_at + delay_hours`. Anything else:
   insert with `state = 'skipped'` and `reason = kind`, so the pending list
   can show "skipped: guest" instead of silently doing nothing.
3. If the insert actually inserted and `ask_profile` is on, DM the new
   joiner (section 9). Store `dm_ts` so the DM can be updated after posting.

No channel is set: nothing is inserted. Enabling Intros never welcomes the
backlog of people who joined before; only `team_join` events from then on.

## 7. When the card is posted

Two things decide it: the new person has had a chance to fill the profile,
and the channel is awake.

A row is **due** when it is `pending` and either:

- `post_after <= NOW()` (the delay ran out), or
- the member saved their profile after joining
  (`member_profiles.updated_at > joined_at` and `updated_by = user_id`).

A due row is **posted** only inside posting hours: between `post_from` and
`post_until` on a working day in the Intros timezone. So someone who joins
at 18:00 on Friday with a 24 hour delay is welcomed at 09:00 on Monday, not
at 18:00 on Saturday to an empty channel.

Default delay is 24 hours: long enough for a first day of laptop setup and
one look at the DM, short enough that the welcome still feels like a
welcome. See open question 2.

"Post it now" on the DM bypasses both the delay and posting hours, because
the person asked.

### The sweep

`plan_jobs` returns one job per workspace with Intros active:

```python
JobSpec(key="sweep", trigger=IntervalTrigger(minutes=10), func=sweep, args=(team_id, bot_token))
```

An interval sweep rather than a cron at the posting hour, because
`reconcile_jobs` compares ids only (`scheduler.py:1783-1791`): a cron whose
hour came from a setting would keep firing at the old hour after an admin
changed it, until the next restart. The sweep reads settings on every run.

Each run:

1. Load settings; stop if no channel, or outside posting hours.
2. Mark `cancelled` any pending row whose member is now inactive.
3. Claim due rows atomically, so two pods during a rolling update cannot
   both post:

   ```sql
   UPDATE intro_welcomes w SET state = 'posting', updated_at = NOW()
   WHERE (w.team_id, w.user_id) IN (
       SELECT team_id, user_id FROM intro_welcomes
       WHERE team_id = %s AND state = 'pending' AND <due>
       ORDER BY joined_at LIMIT 20
       FOR UPDATE SKIP LOCKED)
   RETURNING *;
   ```

4. Post: one card per person when one or two are claimed, one grouped card
   when three or more are claimed in the same run (section 9).
5. Mark `posted` with `channel_id` and `message_ts`, then update the DM.

A crash between steps 3 and 5 leaves a row in `posting`. It is never retried
automatically: a missing welcome can be posted by hand, a duplicate one in a
public channel cannot be taken back. The pending list shows rows stuck in
`posting` for over 15 minutes as "Not sure this posted" with Post and Skip
buttons.

Rate limits: at most 20 claimed per run, posted through the existing
`connect.slack_api` throttle pattern. A bulk import of 200 accounts becomes
grouped cards over a few runs, not 200 posts.

## 8. Settings and dashboard

Intros settings page, editable by a workspace admin or an Intros admin
(`module_admins`, `047_module_admins.sql`):

| Setting | Default | Notes |
|---|---|---|
| Channel | none, required | Picker checks `conversations.info` and warns "Invite @Morgenruf to #channel first" when the bot is not a member (no `chat:write.public`) |
| Delay | 24 hours | 0, 4, 24 or 48 |
| Timezone | the enabling admin's `members.tz` | Own setting, same reasoning as Celebrations: whoever runs Intros may not run standups |
| Posting hours | 09:00 to 17:00 | |
| Working days | Monday to Friday | |
| Welcome guests | off | |
| Ask new members to fill their profile | on | |

Below the settings, a **Pending** list: people waiting to be welcomed, when
their card will go out, and Post now / Skip buttons. Recent skipped and
posted rows (30 days) show with their reason, which answers "why was X not
welcomed" without logs.

## 9. Messages

Warm, short, Donut style, the same voice as the Celebrations messages. Names
are mentions. No pronouns at all, since the profile does not store them.

### Card, full profile

```
👋 Please welcome @Priya to the team!

💼 Product Designer
📍 Berlin
💬 Ask Priya about: bouldering, type design, Rust

Say hi in the thread. 🙌
```

Built as Block Kit: a section with the text and the Slack avatar
(`members.avatar_url`) as accessory, and a context line.

### Card, partial profile

Only present fields are shown; there are no empty labels.

```
👋 Please welcome @Priya to the team!

💼 Product Designer

Say hi in the thread. 🙌
```

### Card, empty profile

Fallbacks, in order, before giving up on a field:

- role: Slack's own `profile.title` ("What I do"), which many workspaces
  already fill in;
- location: none. The timezone would give a city (`hours.zone_city`), but a
  time zone is not where someone lives; see open question 5.

With nothing at all:

```
👋 Please welcome @Priya to the team!
Say hi in the thread and help Priya feel at home. 🙌
```

### Grouped card, three or more

```
👋 Please welcome 4 new people to the team!

@Priya · 💼 Product Designer · 📍 Berlin
@Tom · 💼 Support Engineer
@Ana · 📍 Lisbon
@Kenji

Say hi in the thread. 🙌
```

### DM to the new joiner

Sent when the row is created, if "Ask new members to fill their profile" is
on. The time phrase is computed from when the card is due.

```
👋 Welcome to Acme, Priya!

Tomorrow morning I'll introduce you to the team in #introductions.
Add a few details first so people know what to ask you about.

[ Fill in my profile ]   [ Post it now ]   [ Don't introduce me ]
```

- **Fill in my profile** opens the profile modal from release 1. Saving it
  makes the row due (section 7).
- **Post it now** claims and posts immediately.
- **Don't introduce me** sets the row `skipped`, reason `declined`.

After posting, the DM is updated in place:

```
✅ You're introduced in #introductions. Have a great first week, Priya!
```

After declining:

```
No problem, I won't post anything. You can fill in your profile any time
with /morgenruf profile.
```

With "Ask new members" off, the same DM is not sent, and nothing else is
either.

### Standup's existing welcome

Standup DMs "👋 Welcome to the team!" to anyone who joins a standup channel
(`standup/handlers.py:1373-1379`), including people who have been in the
workspace for years. On a new hire's first day that becomes two welcome DMs
from the same bot. This release rewords it to "👋 Welcome to #channel! I run
the daily standup here..." so there is one welcome to the team and one to
the standup.

## 10. Privacy

- The card only shows what the member (or an admin, per the profile design)
  entered, plus Slack name and avatar which the channel can see anyway.
- The new joiner can decline before anything is posted.
- `intro_welcomes` holds ids, timestamps and a state; no profile data. Rows
  are deleted with the member's profile under the profile's 30 day leaver
  rule, and on uninstall through `ON DELETE CASCADE`. `purge` deletes both
  tables for the workspace.

## 11. Tests

Core:

- `classify`: bot, app user, Slackbot, deleted, external team, multi-channel
  guest, single-channel guest, stored row older than 24 hours, stored row
  from 5 minutes ago (a channel join a moment earlier) still `new`, old
  profile start date, plain new hire.
- The `team_join` listener offers the event only to active modules, and one
  module raising does not stop the next (same shape as
  `test_module_job_sync.py:96`).
- The listener upserts the `members` row and sets `is_guest`; the sync keeps
  `is_guest` current.
- Manifest: `team_join` present in both root manifests, and its scope
  requested (extension of `test_oauth_scope_drift.py`).
- **Connect follow-ups:** a test that queues `_schedule_followups` and then
  runs `sync_module_jobs`, asserting whether the nudge job survives
  (section 2). This belongs in its own Connect fix, but Intros relies on the
  same reconciler so the behaviour must be pinned down first.

Intros:

- A duplicate `team_join` inserts one row and sends one DM.
- Due by delay; due early by profile save; profile edited by an admin does
  not count as the member saving it.
- Posting hours: Friday 18:00 join with 24 hour delay posts Monday 09:00;
  a timezone where it is already Monday posts then.
- Two concurrent sweeps claim disjoint rows (`FOR UPDATE SKIP LOCKED`
  against a real Postgres, like the Connect round tests).
- Crash after claim leaves `posting`, never re-posted by the sweep.
- Member deactivated before posting: `cancelled`.
- Card rendering: full, partial, empty with Slack title fallback, empty with
  nothing, grouped at three.
- No channel set: nothing inserted. Module disabled: listener never calls it.
- Guests skipped by default, welcomed when the setting is on.
- Declining updates the row and the DM; Post it now works outside hours.
- Dashboard: an Intros admin can edit settings; a plain member cannot.

## 12. Deliverables (release 2)

| Surface | Change |
|---|---|
| App, core | `team_join` in `slack-manifest.yaml` and `slack-manifest.json`; `users:read` description; `ModuleSpec.on_member_joined`; single `team_join` listener in `main.py`; `core/newcomers.py`; `members.is_guest` migration and sync update; standup welcome DM reworded |
| App, module | `modules/intros`: migration, settings page with channel check, pending list, `on_member_joined`, 10 minute sweep, card and DM blocks, button handlers |
| Docs | README (Intros section, Coming table, self-host upgrade note: add `team_join` to your Slack app), CHANGELOG, docs.morgenruf.dev Intros page (setup, how new hires are told apart from guests, delay and posting hours, the decline button) |
| Website | `/intros` product page, Donut alternative and compare pages (Intros row), homepage roadmap, `llms.txt` and `llms-full.txt` |

The website deploys only through the Netlify CLI; merging to main does not
deploy it. Roll out outside standup hours, since two schedulers overlap
during a rolling update; the claim in section 7 is what makes that safe for
Intros.

## 13. Decisions (resolved 2026-09-27)

The owner accepted every recommendation:

1. **Stale `app/slack-manifest.*`:** deleted in the Celebrations release;
   the root pair is the only manifest.
2. **Delay:** 24 hours, posted early once the person saves their profile,
   never outside posting hours.
3. **Enterprise Grid moves:** welcomed anyway in v1; "Don't introduce me"
   and the admin Skip cover it.
4. **👋 reaction:** Celebrations adds `reactions:write` to the manifest and
   reacts only when the install has granted it; no workspace is forced to
   reinstall. Intros uses the same rule, so the card gets a 👋 reaction
   wherever the scope is present.
5. **Location:** no fallback from timezone. Role may fall back to Slack's
   `profile.title`.
6. **Guests turned into full members:** out of scope; a "Welcome someone"
   button on the pending list creates a row by hand.
7. **Thread digest:** no.
