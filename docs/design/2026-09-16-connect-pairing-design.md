# Design: Module contract (Phase 0) and Connect pairing (sub-project 1)

Date: 2026-09-16
Status: Approved design, ready for implementation planning
Scope: `app/src` restructure into a module contract, plus the Connect pairing module

## 1. Why

Morgenruf ships a Slack standup bot. The goal is Donut parity: pairing,
watercooler prompts, intros, onboarding buddies, and recognition.

That is five subsystems, not one feature. Building them into the current flat
`app/src` layout would push `handlers.py` and `blocks.py` past 3000 lines each
and make every later module harder than the one before it.

So the work splits into a foundation (a module contract) and a first module
(Connect pairing).

A second goal, stated explicitly by the product owner: adding, removing,
enabling, or disabling a module later must be cheap and must not require
touching core code.

### Non-negotiable constraint

Standup runs in production and teams depend on it daily. Every decision in this
document is subordinate to the rule that standup behavior does not change and
standup availability is not interrupted. Section 9 covers how that is enforced.

## 2. Current state (verified 2026-09-16)

| Fact | Value |
|---|---|
| Test suite | 530 tests, all passing, 5.6s |
| Total coverage | 43% |
| `handlers.py` | 1957 lines, 29% covered |
| `blocks.py` | 1782 lines, 40% covered |
| `db.py` | 1770 lines, 50% covered |
| `scheduler.py` | 1518 lines, 53% covered |
| `dashboard.py` | 1497 lines, 57% covered |
| Migrations | 28 applied, flat `migrations/*.sql`, key is bare filename |
| Deployment | `replicaCount: 1`, no `strategy:` block, migrations in an initContainer |
| Imports | flat, via `sys.path.insert` in `main.py` and in all 28 test files |
| Test config | no `conftest.py`, no pytest config |

Findings that shape the plan:

1. `src/app.py` is dead code. No importer, and its relative import
   (`from .handlers import`) cannot resolve under the current flat path scheme.
2. `adapters/slack_adapter.py` is dead code. `SlackAdapter` has no importer.
   Standup calls `WebClient` directly throughout.
3. `main.py:137` and `main.py:144` already register `mcp_bp` and
   `google_chat_bp` as conditional, feature-flagged blueprints. That is a
   hand-rolled module registry, implemented twice.
4. `kudos` (migration 010, `db.py:1560-1607`, DM and slash command handlers)
   already implements Donut's Recognition pillar. It is shipped but not
   packaged as a module.
5. `scheduler.py:1458` builds a bare `BackgroundScheduler()` with an in-memory
   job store, no leader election and no lock.
6. One test file carries the comment "Earlier test modules leave MagicMock
   stubs in sys.modules". Test isolation already leaks between modules.
7. **The manifest and the OAuth authorize URL request different scopes.**
   `slack-manifest.yaml` declares `app_mentions:read`, `channels:join`,
   `chat:write.public` and `team:read`, none of which appear in `_SCOPES` in
   `oauth.py:28`. `_SCOPES` additionally requests `commands`, which the
   manifest omits. The authorize URL governs what is actually granted, so
   OAuth-installed workspaces do not hold those four scopes. Consequence:
   the `app_mention` listener at `handlers.py:1339` is dead for those
   workspaces. This is a pre-existing bug, tracked separately, and it is the
   reason `granted_scopes` must be read from the `oauth.v2.access` response
   rather than inferred from `_SCOPES`.

## 3. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Build inside Morgenruf, not as a separate product | Slack OAuth, scheduler, timezone handling, dashboard, Helm and release pipeline already exist. A second Slack app doubles install friction, review, docs and support for a solo maintainer. |
| D2 | Build order: Phase 0, then Pairing, then Watercooler, Intros, Onboarding buddies, Celebrations | Pairing is the competitive core and has the hardest logic. The rest get cheaper once it exists. Celebrations is last because it is blocked on a PII collection problem, not a code problem. |
| D3 | Module contract, not a plain package split | Adding or removing a module must be one directory plus one registry line. |
| D4 | One deployable, one Slack app | A second container doubles ops surface at current install count. |
| D5 | Standup, mcp, google_chat and kudos all convert to the contract in Phase 0 | One registration mechanism. A contract designed against four consumers is far likelier to be right than one designed against one. |
| D6 | Pairing pool comes from channel membership | Donut's own model. Reads membership via `conversations.members`, which needs only `channels:read`, already granted. Connect does not post to the channel, so `channels:join` is not required (see Finding 7: it is declared in the manifest but never actually requested at install). Pool grows automatically, no admin maintenance. |
| D7 | Pairs, with the odd member joining a trio. Avoid repeats until the pool is exhausted | Nobody ever sits out. Matches Donut behavior, which is what users notice when it is wrong. |
| D8 | New scopes are opt-in per workspace; Connect is gated behind re-auth | Standup keeps working on the existing token. Existing installs are untouched until their admin chooses to enable Connect. |
| D9 | Connect calls Slack directly, not through `PlatformAdapter` | `PlatformAdapter` has no group DM concept, Google Chat has no MPIM equivalent, and the abstraction is at 0% coverage with one caller. Revisit when a second platform actually needs pairing. |
| D10 | UI reference is Donut for Slack copy and flow, existing dashboard for chrome | Same app, so a second visual language would be worse than consistency. |
| D11 | Scheduler leader lock is deferred, with a deploy-window requirement | Product owner decision. See Accepted Risk AR1. |
| D12 | Standup's substring message patterns stay unchanged; Connect avoids those words | Bolt's `@app.message("skip")` is a substring match, so any Connect command containing help, standup or skip fires standup's handler. Anchoring standup's patterns would narrow what live users can type. Connect uses button-only opt-out instead. |

## 4. Phase 0: the module contract

### 4.1 Layout

```
app/src/
  main.py                    # wiring only: build registry, hand to core
  core/                      # knows nothing about any specific module
    db.py slack.py scheduler.py oauth.py
    roster.py                # NEW, shared eligibility
    modules.py               # NEW, ModuleSpec + registry + activation
    dm_router.py             # NEW, single message.im listener
    installation_store.py session_store.py state.py config.py url_guard.py
    migrations/              # installations, members, workspace_modules
    dashboard/               # blueprint shell, auth, nav rendering
  modules/
    __init__.py              # REGISTRY = (standup.MODULE, kudos.MODULE,
                             #             mcp.MODULE, google_chat.MODULE,
                             #             connect.MODULE)
    standup/    __init__.py handlers.py blocks.py jobs.py migrations/ ...
    kudos/      __init__.py handlers.py migrations/
    mcp/        __init__.py http.py server.py
    google_chat/__init__.py handler.py adapter.py
    connect/    __init__.py matcher.py jobs.py handlers.py blocks.py
                dashboard.py slack_api.py migrations/
```

### 4.2 The contract

```python
@dataclass(frozen=True)
class ModuleSpec:
    name: str  # "standup" | "connect" | ...
    required_scopes: tuple[str, ...]
    migrations_dir: Path | None
    register_slack: Callable[[App], None] | None
    register_routes: Callable[[Blueprint], None] | None
    plan_jobs: Callable[[JobContext], list[JobSpec]] | None
    claim_dm: Callable[[DMContext], bool] | None
    purge: Callable[[str], None] | None  # team_id -> delete module data
    nav: tuple[NavItem, ...]
    default_enabled: bool
```

Core never imports a module by name. Adding a module is one directory plus one
line in `REGISTRY`.

### 4.3 Activation

A module is active for a workspace only if all four hold, checked in order:

1. Deploy allowlist: `MORGENRUF_MODULES` env (absent means all registered).
   This lets a build ship with Connect present but dark.
2. Scopes granted: `installations.granted_scopes` covers `required_scopes`.
3. Workspace toggle: `workspace_modules.enabled` for that team and module.
4. `default_enabled` when no `workspace_modules` row exists.

### 4.4 Jobs

Core owns the single APScheduler. Job ids are namespaced
`{module}:{team_id}:{job}`. The reconcile loop asks each active module for its
desired jobs, diffs against live jobs, and adds or removes. Disabling a module
makes its jobs disappear on the next reconcile with no bespoke teardown code.

### 4.5 Migrations

The runner scans `core/migrations/` plus each registered module's
`migrations/`. `schema_migrations.filename` stays the bare basename, so the 28
rows already applied in production remain valid after the files move. No
backfill, no data migration, no risk to live installs.

A test asserts that migration basenames are globally unique across modules, so
the flat key cannot collide.

### 4.6 DM routing (the trap)

Standup listens on `message.im` for standup answers. Connect needs DM replies
too ("skip this round"). Bolt fires every matching listener, so both modules
would process the same message and standup would treat "skip this round" as a
standup answer.

Modules therefore do not register raw `message` listeners. Core's `dm_router`
owns the single listener and offers each message to every active module's
`claim_dm` in priority order. First claim wins. No claim falls through to the
existing help text. Standup's current DM handling moves behind `claim_dm`
unchanged.

The same class of collision applies to interactivity. New action_ids are
namespaced (`connect:optout`). Existing standup action_ids stay bare, because
changing them would break buttons in Slack messages already delivered. A test
requires the prefix on anything new.

### 4.7 Shared roster

`core/roster.py` answers one question for the whole product:

```python
eligible_members(team_id, channel_id=None) -> list[Member]
```

Filters bots, deactivated users, `user_away` (the existing vacation table), and
per-module opt-outs. Standup does this inline today. Phase 0 extracts it and
points standup at it, covered by the existing participation tests.

### 4.8 Re-auth gating

Migration adds `installations.granted_scopes TEXT[]`, populated from the OAuth
response on install and re-install. Helper `has_scopes(team_id, [...]) -> bool`.

The dashboard shows an "Enable Connect" card when scopes are missing, linking
to a fresh OAuth with the extended scope set. Connect routes and jobs no-op for
workspaces that have not re-authorized. Standup code paths never check scopes,
so existing installs are untouched.

Scopes added for Connect: `mpim:write` (open the group DM), `mpim:history`
(detect silence before nudging), `users.profile:read` (name, title and photo
for the intro card). These are added to both `slack-manifest.yaml` and the
Connect variant of `_SCOPES`, because Finding 7 shows those two lists have
already drifted apart once.

`granted_scopes` is populated from the `scope` field of the `oauth.v2.access`
response, which is the authoritative record of what Slack actually granted.
It is never inferred from the requested scope list.

### 4.9 Dead code removed in Phase 0

`src/app.py` and `src/adapters/slack_adapter.py`. Both verified to have no
importers.

## 5. Connect data model

All tables are prefixed `connect_`, so the module owns a clean namespace and
`purge(team_id)` is five statements.

```sql
connect_programs                    -- one per channel
  id, team_id, channel_id, name,
  interval_weeks INT,               -- 1 = weekly, 2 = biweekly
  day_of_week INT, hour INT, minute INT, timezone TEXT,
  enabled BOOL, created_at
  UNIQUE (team_id, channel_id)

connect_rounds
  id, program_id, team_id, scheduled_for TIMESTAMPTZ,
  state TEXT,                       -- pending | matched | delivered | closed
  member_count INT, created_at
  UNIQUE (program_id, scheduled_for)

connect_matches
  id, round_id, team_id,
  member_ids TEXT[],                -- length 2, or 3 for the odd-count trio
  mpim_channel_id TEXT,
  delivered_at, nudged_at,
  met BOOL NULL

connect_pair_history
  program_id, member_a, member_b,   -- normalized so member_a < member_b
  times_paired INT, last_round_id
  PRIMARY KEY (program_id, member_a, member_b)

connect_optouts
  team_id, program_id, user_id,
  mode TEXT,                        -- off | paused
  paused_until DATE
  PRIMARY KEY (team_id, program_id, user_id)
```

Notes:

- `member_ids TEXT[]` covers pairs and trios in one shape. A trio writes all
  three edges to `connect_pair_history`, so repeat avoidance stays correct
  without a separate trio concept.
- `UNIQUE (program_id, scheduled_for)` is the idempotency guard. Duplicate job
  fires and scheduler restarts are a known failure mode in this codebase, so
  double-matching is made impossible in the database rather than in application
  logic.
- Every `connect_` table carries `team_id` with a foreign key to
  `installations(team_id) ON DELETE CASCADE`, matching the existing
  convention. Uninstall therefore cleans up automatically through
  `delete_installation` (`db.py:1759`), and `ModuleSpec.purge` exists for the
  narrower case of a workspace disabling the module and asking for its data to
  be removed.
- No message content is stored. Only user ids, the MPIM channel id and
  timestamps. This keeps the self-hosted privacy position honest and keeps
  `purge` trivial.
- `met` is the only analytics collected. It drives the single dashboard number
  that indicates whether the feature works.
- Vacation is read, never copied. Matching calls `core.roster.eligible_members`,
  which already excludes `user_away`.

## 6. Matching engine

A pure function with no I/O, so it is fully unit-testable:

```python
def match(pool: list[str], history: dict[tuple[str, str], PairStat], seed: int) -> list[list[str]]
```

- Cost of pairing a and b is `times_paired`, plus a heavy penalty if they were
  paired within the last few rounds. Never-paired pairs cost 0, so "no repeats
  until the pool is exhausted" falls out of the cost function rather than
  needing a special case.
- Greedy lowest-cost selection, O(n^2), fine to roughly 500 members. Not
  optimal the way a blossom max-weight matching would be, but optimality only
  matters once most pairs have already met, and it would cost a `networkx`
  dependency. The swap point is isolated inside this one function.
- Odd count: the leftover member is appended to whichever existing pair they
  have the lowest combined cost with, forming a trio.
- `seed` derives from the round id, not the clock. Re-running a round produces
  the same matching, which makes the matcher reproducible in tests and
  debuggable in production, and means a retried job cannot silently produce a
  different pairing.

## 7. Round lifecycle

State machine: `pending -> matched -> delivered -> closed`

**Trigger.** APScheduler cron cannot express "every 2 weeks" cleanly, because
its `week` field is an ISO week number that drifts at year boundaries. So the
job fires weekly on `day_of_week` at `hour:minute` in the program timezone, and
the job body checks whether `interval_weeks` have elapsed since the last round.
This self-heals after downtime: a missed week starts the round late rather than
skipping it.

**Delivery.** A 200-member channel produces 100 group DMs. `conversations.open`
is Tier 3 (roughly 50/min) and `chat.postMessage` is roughly 1/sec per channel.
Naive delivery gets rate limited and part of the workspace silently never hears
from the bot. Delivery is therefore chunked with backoff, each match's
`delivered_at` is written as it succeeds, and the job is resumable: a restart
mid-delivery picks up only undelivered matches.

**Nudge.** One job at +3 days. Reads the MPIM (the purpose of `mpim:history`)
and posts a single nudge only if no member has posted. Never more than once.

**Close.** At round end each match receives a "did you two meet?" prompt with
two buttons, writing `met`.

**Opt-out.** Button-only, through the `Skip this round` and `Pause` actions on
the intro message, never a DM keyword. Per decision D12, Connect cannot use a
DM command containing help, standup or skip, because standup's bare string
patterns are substring matches and would claim it. Paused members are filtered
by `connect_optouts` before matching.

## 8. UI

Donut for Slack copy and flow, existing Morgenruf dashboard for chrome.

**MPIM intro message**, short, warm, one clear action:

> Hi @A and @B, you have been matched for a coffee chat this week.
> *Icebreaker:* <rotating prompt>
> `[ Find a time ]` `[ Skip this round ]`

**Nudge** (+3 days, only if the MPIM is silent): one line, no guilt, a fresh
icebreaker.

**Close prompt:** "Did you two get a chance to meet?" `[ Yes ]` `[ Not yet ]`

**Dashboard** at `/m/connect/`, nav item visible only when the module is active:

- Programs list: channel, cadence, next round, pool size, met-rate
- Program editor: channel picker, `interval_weeks`, weekday, time, timezone,
  reusing the standup schedule editor's form patterns
- Round history: date, matches, delivered, met-rate
- Opt-out list

## 9. Production safety

This section is the point of the document. Standup is live and teams use it
daily.

### 9.1 Invariant

Standup behavior does not change in Phase 0. Enforced two ways:

1. The 530-test suite must pass before and after every commit.
2. Coverage of the files that move is too low to rely on tests alone
   (`handlers.py` at 29%, `blocks.py` at 40%). So each moved file is `git mv`
   plus import-line rewrites and nothing else, verified by a one-off check that
   parses each moved module's AST before and after, strips `Import` and
   `ImportFrom` nodes, and asserts the trees are identical. Any accidental
   logic edit fails loudly.

Real logic changes (standup's `claim_dm`, roster extraction) land as separate,
reviewable commits on top, each with its own tests.

### 9.2 Zero downtime

`replicaCount: 1` with no `strategy:` block means Kubernetes defaults apply:
maxUnavailable 25% resolves to `floor(1 * 0.25) = 0`, maxSurge 25% resolves to
`ceil(1 * 0.25) = 1`. The new pod must pass readiness before the old pod is
terminated. There is no serving gap.

### 9.3 Migrations are additive only

Phase 0 adds tables (`workspace_modules`, `connect_*`) and one column
(`installations.granted_scopes TEXT[]`). Adding a nullable column with no
default is metadata-only in modern Postgres: no table rewrite, and the
ACCESS EXCLUSIVE lock is held for microseconds on a small table.

Migrations run in an initContainer before the new pod starts, while the old pod
is still serving. Additive-only means the currently-running code is unaffected
by the new schema.

### 9.4 The Helm chart compatibility trap

`helm/morgenruf/templates/deployment.yaml:28` hardcodes
`command: ["python", "src/migrate.py"]`. That path lives in the chart, not the
image. Moving to a package entrypoint would mean anyone who pulls the new image
while pinning an older chart gets an initContainer that crashes, so the pod
never starts. That is an outage for self-hosted users, caused by us.

Mitigation: `src/migrate.py` stays as a thin compatibility shim that imports and
calls the real runner. Old chart plus new image keeps working. The same
treatment applies to any other path the chart references. This is a hard
requirement, not an optimization.

### 9.5 Rollback

Because migrations are additive and the old code never reads the new tables or
column, rollback is an image revert. No down migrations, no data restore, no
coordination. This property must be preserved in every Phase 0 release.

### 9.6 Release sequencing

Each release is independently revertible and ships behind the previous one.

| Release | Content | User-visible change |
|---|---|---|
| R1 | `conftest.py` with shared path setup and a `sys.modules` restore fixture, remove the 28 per-file `sys.path.insert` lines, delete `src/app.py` and `adapters/slack_adapter.py`, add the AST-equivalence harness | None |
| R2 | Package split, mechanical file moves only, `migrate.py` shim, entrypoint change | None |
| R3 | `core/modules.py`, `dm_router`, convert standup, kudos, mcp and google_chat to `ModuleSpec` | None |
| R4 | `core/roster.py` extraction, `granted_scopes` column, re-auth card | Dashboard gains an "Enable Connect" card |
| R5 | Connect module, present but dark. `default_enabled=False` is the primary guard. Because an absent `MORGENRUF_MODULES` means all registered modules, keeping Connect dark at the deploy level requires setting the variable explicitly (for example `MORGENRUF_MODULES=standup,kudos,mcp,google_chat`) | None |
| R6 | Connect enabled for opted-in workspaces | Connect available |

R1 through R3 ship zero user-visible change. If anything is wrong, it shows up
as a failing test or a crash on startup, not as a silently broken standup.

### 9.7 Deploy checklist (every Phase 0 release)

1. Deploy outside any workspace's standup or report window (see AR1)
2. Full suite green, AST-equivalence check green
3. Confirm the initContainer completed and `schema_migrations` gained only the
   expected rows
4. Confirm pod readiness before the old pod terminated (no gap in `/healthz`)
5. Confirm zero restarts and zero errors for 15 minutes
6. Trigger one manual standup in a test workspace and confirm delivery
7. Confirm chart and image versions are compatible for self-hosted users

## 10. Testing

- Matcher is pure, so property-based tests: everyone appears exactly once,
  trios only on odd counts, no repeat until the pool is exhausted, same seed
  gives the same result
- Lifecycle tests against a mocked Slack client, including a mid-delivery
  restart
- Contract tests: new action_ids are namespaced, migration basenames are
  globally unique, `purge(team_id)` covers every `connect_` table
- The AST-equivalence check gating every refactor commit
- Failure-mode tests: token revoked, `channel_not_found`, rate limited,
  deactivated user mid-round, fewer than 2 eligible members

## 11. Failure modes and defined behavior

| Failure | Behavior |
|---|---|
| Token revoked | Existing `is_dead_install` path |
| `channel_not_found` | Disable the program, surface a dashboard warning, stop retrying |
| Rate limited | Back off honoring `Retry-After`, resume from undelivered matches |
| User deactivated mid-round | Drop from pool, continue the round |
| Fewer than 2 eligible members | Skip the round silently. Nobody receives a DM telling them they had nobody to meet |
| Duplicate job fire | Blocked by `UNIQUE (program_id, scheduled_for)` |

## 12. Accepted risks

**AR1: duplicate scheduler during rollout.** `scheduler.py:1458` builds a bare
`BackgroundScheduler()` with no leader election or lock, so during the rolling
update surge window the old and new pods both run schedulers for roughly 30 to
60 seconds. A standup or report fire time landing in that window produces
duplicate DMs.

This is pre-existing and applies to every release already shipped, including
v1.6.0. A Postgres advisory lock (roughly 30 lines) was proposed and
deliberately deferred by the product owner.

Mitigation, which is now a hard release requirement: deploy outside standup and
report windows. It also blocks `replicaCount > 1` until fixed. Revisit before
Connect adds a second family of scheduled jobs.

**AR2: low coverage on the largest moved files.** `handlers.py` at 29% and
`blocks.py` at 40%. Mitigated by the AST-equivalence check in 9.1 rather than
by writing characterization tests first.

## 13. Out of scope

Watercooler, Intros, Onboarding buddies and Celebrations. Each gets its own
spec. See `2026-09-16-connect-roadmap.md`.
