# Watercooler questions

Status: approved in chat 2026-10-02, spec for review.

## Why

Activation is the problem: 1 of 18 outside workspaces uses Morgenruf as a team.
Standups need setup and a habit before anything shows up in Slack. A watercooler
question posts to a channel on day one with nothing else configured, so a new
workspace sees Morgenruf doing something useful within hours of installing.

Reference product: Donut Watercooler. A question lands in a channel on a
schedule and people reply in the thread. Donut keeps custom questions and more
than one channel on its paid plans; here both are free.

## Constraints

- Slack Marketplace review is in progress. No new scopes, slash commands,
  shortcuts or event subscriptions. Entry points are `/morgenruf watercooler`,
  an App Home button and the dashboard.
- No `channels:history`, so the bot cannot read thread replies. No reply
  counts, no "3 people answered" follow-ups in this version.
- `reactions:write` is optional. Used only where the installation granted it,
  as celebrations already does.

## Scope

In:

1. A built-in bank of about 150 questions with stable keys, in four
   categories: `light`, `work`, `remote`, `this_or_that`.
2. Custom questions per workspace, added, edited and archived by the module's
   admins.
3. Hiding built-in questions per workspace. Hiding never affects another
   workspace.
4. Several channels per workspace, each with its own days, time, timezone,
   question source and categories.
5. A 🙋 reaction on each post when `reactions:write` is granted.
6. Setup from the dashboard, `/morgenruf watercooler` and App Home.
7. A checkbox in the 1.9.13 quick start modal: "Also post a watercooler
   question here Mon, Wed, Fri", ticked by default.
8. Post counts in the Monday report and `workspace_history`.

Out (later, some after Marketplace approval):

- Team submitted questions with approval.
- Reply counts and recaps (need `channels:history`).
- An "Answer" button.

## Module

`app/src/modules/watercooler/`, the same shape as `celebrations`:

| File | Job |
|---|---|
| `__init__.py` | `ModuleSpec(name="watercooler", required_scopes=(), default_enabled=False, delegable=True, ...)` |
| `bank.py` | The built-in questions: `Question(key, category, text)`. No I/O. |
| `rotation.py` | Picks the next question. Pure, tested with plain lists. |
| `db.py` | Reads and writes the four tables, `purge(team_id)`. |
| `jobs.py` | `plan_jobs` (one job per active channel) and `run_post`. |
| `messages.py` | The Block Kit for the post and the owner DM. |
| `handlers.py` | `/morgenruf watercooler`, the setup modal, App Home button. |
| `dashboard.py` | JSON routes for the dashboard tab. |
| `schemas.py` | Request validation. |
| `migrations/0NN_watercooler.sql` | The tables below. |

Enabling the module from the quick start checkbox or the first channel setup
turns it on for the workspace. The installer stays an admin of it, as for every
delegable module.

## Data

```sql
CREATE TABLE watercooler_channels (
    team_id     TEXT NOT NULL,
    channel_id  TEXT NOT NULL,
    days        TEXT NOT NULL DEFAULT 'mon,wed,fri',
    post_time   TEXT NOT NULL DEFAULT '10:00',      -- HH:MM, local
    timezone    TEXT NOT NULL,                      -- canonical IANA name
    source      TEXT NOT NULL DEFAULT 'both',       -- builtin | custom | both
    categories  TEXT NOT NULL DEFAULT 'light,work,remote,this_or_that',
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    paused_reason TEXT,                              -- e.g. not_in_channel
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, channel_id)
);

CREATE TABLE watercooler_questions (                -- custom, per workspace
    id          BIGSERIAL PRIMARY KEY,
    team_id     TEXT NOT NULL,
    text        TEXT NOT NULL CHECK (char_length(text) BETWEEN 5 AND 300),
    archived    BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE watercooler_hidden (                   -- built-ins hidden per workspace
    team_id     TEXT NOT NULL,
    question_key TEXT NOT NULL,
    PRIMARY KEY (team_id, question_key)
);

CREATE TABLE watercooler_posts (
    team_id     TEXT NOT NULL,
    channel_id  TEXT NOT NULL,
    posted_on   DATE NOT NULL,                      -- channel-local date
    question_ref TEXT NOT NULL,                     -- 'b:<key>' or 'c:<id>'
    message_ts  TEXT,
    PRIMARY KEY (team_id, channel_id, posted_on)
);
```

- The `watercooler_posts` primary key is the claim: the row is inserted before
  the message is sent, so a restart or a second pod cannot double post. Same
  pattern as celebrations. "Post one now" uses the claim too, so it counts as
  that day's post and the scheduled one is skipped.
- Posts older than 365 days are purged nightly. Rotation only needs the current
  cycle.
- Limits: 20 channels and 500 custom questions per workspace.
- `purge(team_id)` deletes all four tables' rows on uninstall.

## Choosing a question

Pool for a channel = built-ins in the channel's categories, minus hidden ones
(if `source` is `builtin` or `both`), plus non-archived custom questions (if
`source` is `custom` or `both`).

1. Drop everything this channel posted since its cycle began.
2. If nothing is left, start a new cycle: the whole pool is available again,
   except the last question posted.
3. Pick at random from what is left.

If the pool is empty (for example `custom` with no custom questions), skip the
post and DM the channel's owner once, pointing at the dashboard.

"Used in this cycle" is computed by walking the channel's posts newest first
and collecting refs that are still in the pool, stopping at the first repeat or
once every pool question is collected. No cycle counter is stored, so editing
the pool (hiding, archiving, adding) never needs a reset.

## Posting

- `plan_jobs` makes one cron job per active channel at `post_time` in
  `timezone` on the channel's days.
- At fire time, skip if the workspace calendar says the local date is not a
  working day or is a company holiday.
- Message: header "☕ Watercooler", the question in bold, context line
  "Reply in the thread 👇". Then add 🙋 if `reactions:write` was granted.
- `not_in_channel` or `channel_not_found`: set `active = FALSE`,
  `paused_reason`, release the claim, and DM `created_by` once: "Add
  @Morgenruf to #channel (channel details, Integrations, Add apps), then press
  Resume." Other Slack errors: log, release the claim, no retry that day.

## Setup surfaces

Dashboard tab "Watercooler":

- Channels table: channel, days, time, source, status. Add, edit, pause,
  resume, remove, "Post one now".
- Question bank: grouped by category, each built-in with a hide toggle and a
  "Hidden (n)" filter.
- Our questions: list with add, edit, archive.

Slack:

- `/morgenruf watercooler` opens a modal: channel picker, days, time (timezone
  defaults to the person's). Submitting creates or updates that channel's row
  and enables the module. The modal links to the dashboard for the bank.
- App Home: a "Start watercooler" button opening the same modal.
- Quick start modal: the new checkbox creates a row for the chosen channel with
  defaults (Mon, Wed, Fri, 10:00, installer's timezone, both sources).

Only the module's admins can do any of this. Others get the usual "ask an
admin" message.

## Numbers

- `workspace_history` gets `watercooler_posts` (count for the day).
- The Monday report lists watercooler posts per workspace for the week.

## Testing

- `bank.py`: keys unique, texts within length, every category non-empty.
- `rotation.py`: no repeat inside a cycle, cycle restart avoids the last
  question, hidden and archived never chosen, empty pool returns none.
- Jobs: holiday and non-working day skip, claim prevents a second post, "Post
  one now" then scheduled run posts once, `not_in_channel` pauses and DMs once,
  reaction only when the scope is granted.
- Handlers: non-admin refused, modal submit validates time, days and channel.
- Dashboard routes: hide toggles scoped to the workspace, limits enforced.
- Frontend: the tab renders, hide toggle and custom question add work.

## After shipping

- Website roadmap card and changelog.
- Mention in the Slack listing only after Marketplace approval.
