# Design: Member profile (core) and Celebrations (sub-project 5)

Date: 2026-09-27
Status: Draft, decisions agreed with the product owner, ready for review
Scope: a member profile in core, then the Celebrations module that reads it.
Intros and onboarding buddies are listed for order only; each gets its own spec.

## 1. Why

Celebrations (birthdays and work anniversaries) was placed last in
`2026-09-16-connect-roadmap.md` because it is blocked on data, not code.
Slack does not hold the dates we need:

- There is no standard birthday field in a Slack profile.
- Start date exists only on some Enterprise Grid plans.
- Custom profile fields are defined per workspace by admins, so every
  workspace differs and most have none.

Morgenruf also has no place for a member to describe themselves. The
`members` table (`001_initial.sql`) is a mirror of the Slack roster: name,
email, tz, avatar, active, vacation. The channel sync owns it and would
overwrite anything else stored there.

So the profile comes first, as core, because three modules read it:

| Reader | Fields it needs |
|---|---|
| Intros (sub-project 3) | role, location, ask me about |
| Onboarding buddies (sub-project 4) | start date, role, location |
| Celebrations (sub-project 5) | birthday, start date, opt-out |

## 2. Delivery order

1. **Member profile** (this document, sections 3 to 6)
2. **Intros**: `team_join` listener and a welcome card built from the profile
3. **Celebrations** (this document, section 7)
4. **Onboarding buddies**: new hire paired with a buddy using the Connect
   matcher, plus a checklist. Absorbs "Onboarding journeys" from `ROADMAP.md`.

Each release ships app, docs and website together (section 9).

## 3. Data model

Migration `051_member_profiles.sql`, in core (`app/src/core/migrations`),
since no single module owns it.

```sql
CREATE TABLE IF NOT EXISTS member_profiles (
    team_id       TEXT NOT NULL REFERENCES installations(team_id) ON DELETE CASCADE,
    user_id       TEXT NOT NULL,
    birth_month   SMALLINT CHECK (birth_month BETWEEN 1 AND 12),
    birth_day     SMALLINT CHECK (birth_day BETWEEN 1 AND 31),
    start_date    DATE,
    role          TEXT,
    location      TEXT,
    ask_me_about  TEXT,
    celebrate     BOOLEAN NOT NULL DEFAULT TRUE,
    nudged_at     TIMESTAMPTZ,
    left_at       TIMESTAMPTZ,
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id),
    CHECK ((birth_month IS NULL) = (birth_day IS NULL))
);
```

Decisions:

- **Separate table, not columns on `members`.** The sync owns `members`; a
  separate table means it can never overwrite what a person typed.
- **No birth year, ever.** Day and month only. No Celebrations message needs
  an age, and dropping the year removes the sensitive part.
- **`start_date` keeps the year**, because anniversaries count years.
- **`celebrate` defaults to TRUE.** Opt-out, not opt-in (section 5).
- **`updated_by`** records whether the member or an admin last wrote the row,
  so the dashboard can show "set by admin" and the member can correct it.
- A 29 February birthday is celebrated on 28 February in non-leap years.

## 4. Entry points

All four write through one function, `db.upsert_member_profile`, with the
same validation (`schemas.MemberProfile`).

| # | Where | Who | Notes |
|---|---|---|---|
| 1 | App Home, "Your profile" section with an Edit button | member | Main path. App Home is already enabled in the manifest. |
| 2 | `/morgenruf profile` slash command | member | Opens the same modal. New `/morgenruf` command; `profile` is its first subcommand. |
| 3 | Dashboard, "My profile" page | member | Any member can already sign in (`dashboard.py:143`); non-admins get `role: "member"` from `/dashboard/api/me`. |
| 4 | Dashboard, Members page | admin | Edit any row, CSV import, completion count, "Ask for dates" button. |

### Modal fields

```
Your profile
Birthday        [ Month ] [ Day ]
Started on      [ date picker ]
Role            [ text, 80 chars ]
Location        [ text, 80 chars ]
Ask me about    [ text, 200 chars ]
[ ] Don't celebrate me publicly
                         [ Cancel ] [ Save ]
```

### App Home section

```
Your profile                                 [ Edit ]
🎂 14 March   🗓️ Joined Mar 2023   📍 Berlin
Ask me about: Rust, bouldering
```

With no data yet it shows one line and the Edit button:
"Add your birthday and start date so the team can celebrate with you."

### CSV import

Columns: `email,birthday,start_date`. `birthday` accepts `MM-DD` or a full
date (the year is dropped on import). Rows match members by email, since
admins export from an HR tool that knows emails, not Slack ids. The import
previews matched, unmatched and invalid rows before writing, and never
overwrites a value the member set themselves (`updated_by = user_id`)
unless the admin ticks "overwrite member entries".

## 5. Privacy

Agreed rules, chosen so the data actually gets filled without building a
consent system:

- **Admins may import and edit** birthdays and start dates. HR already holds
  them; this is how most of a workspace gets covered on day one.
- **Celebrate by default.** Anyone with a date on file is celebrated.
- **One-click opt-out.** "Don't celebrate me" in the modal, the nudge DM and
  the dashboard. The data stays; nothing is posted.
- **Member can clear their own dates** from the modal or dashboard.
- **No birth year stored**, including on CSV import.
- **Removed when someone leaves.** When `set_members_active` flips a member
  to inactive, the profile gets `left_at = NOW()`. A nightly job deletes rows
  with `left_at` older than 30 days. Reactivation within 30 days clears
  `left_at`, so a Slack deactivate and reactivate does not lose data.
- **Uninstall** removes everything through the existing
  `installations ON DELETE CASCADE`.
- Admins can see all fields. Hiding birthdays from the admins who imported
  them adds complexity and protects nothing.

The privacy page on the website states the fields stored, that the year is
never stored, and the 30 day removal. It ships in the same release.

## 6. Nudging members for dates

- **One-time DM** to every active member with no birthday and no start date,
  sent when the workspace enables Celebrations (not on profile release, so
  nobody is asked for data that nothing uses yet). `nudged_at` prevents a
  second send.
- **Admin "Ask for dates"** button on the Members page. It DMs only members
  still missing dates, shows a preview and the count first, and is limited
  to once per member per 30 days.
- **On channel join**: a member joining the celebrations channel gets the
  same DM if they have no dates.

DM text:

```
👋 Hi Priya! Your team celebrates birthdays and work
anniversaries in #celebrations.

Add yours so nobody misses it. Only day and month are kept.

[ Add my dates ]   [ Skip me ]
```

"Add my dates" opens the modal. "Skip me" sets `celebrate = FALSE`.

## 7. Celebrations module

A module under `app/src/modules/celebrations`, registered with `ModuleSpec`
like `kudos`. Default disabled; an admin enables it and picks a channel.

The module is `delegable=True`, so a workspace admin can make the HR person
a Celebrations admin (the existing `module_admins` grant) without giving
them the rest of the workspace. Everything in this section marked "HR sets"
is editable by a workspace admin or a Celebrations admin.

### Settings

| Setting | Who | Default |
|---|---|---|
| Channel | HR sets | none, required to enable |
| Timezone | HR sets | none, required to enable. Not shared with standup |
| Post time | HR sets | 09:00 in the Celebrations timezone |
| Working days | HR sets | Monday to Friday |
| Holidays | HR sets | empty list |
| Birthdays on | HR sets | on |
| Anniversaries on | HR sets | on |

Timezone is its own setting because the people who run standups and the
people who run celebrations are often different, and a company celebrates
on one clock even when standup teams span several.

### Working days and holidays

HR keeps a list of company holidays (date and name) on the Celebrations
settings page, with add, remove and CSV import (`date,name`). Morgenruf does
not ship a holiday calendar; the company's own list is the only source.

Rule: a celebration that falls on a non-working day (outside the working
days, or on a listed holiday) is posted on the **last working day before
it**. Examples with Monday to Friday working days:

| Celebration on | Posted on | Wording |
|---|---|---|
| Saturday | Friday | "Tomorrow is..." |
| Sunday | Friday | "On Sunday it's..." |
| Monday, a listed holiday | Friday | "On Monday it's..." |
| Christmas week, 24 to 26 Dec all holidays | 23 Dec | "On 25 December it's..." |

Working days cover teams whose week is not Monday to Friday (for example
Sunday to Thursday).

Working days and holidays are a **core workspace calendar**, not
Celebrations data, because Onboarding buddies reads the same calendar (see
`2026-09-27-onboarding-buddies-design.md`, decision 4) and one module must
not read another's settings. Core owns:

- `workspace_holidays`: `team_id`, `date`, `name`,
  `PRIMARY KEY (team_id, date)`. Holidays older than a year are purged.
- `working_days` on the workspace config, default Monday to Friday.

It is edited from the Celebrations settings page in this release, by a
workspace admin or a Celebrations admin. Core exposes
`is_working_day(team_id, date)` and `previous_working_day` /
`next_working_day` helpers; Celebrations uses the previous one.

### Job

Once a day at the post time in the Celebrations timezone, per workspace,
only on working days:

1. Collect members who are active, have `celebrate = TRUE`, and have a
   birthday or start date anniversary today, or on any non-working day
   between today and the next working day.
2. Skip start dates less than one year ago.
3. Post one message per kind per day (birthdays grouped, anniversaries
   grouped), then add the 🎉 reaction as the bot so people pile on. The
   reaction needs `reactions:write`, a new scope: it is added to the
   manifest, and the bot reacts only when the installation has granted it.
   The post goes out either way, so no workspace is forced to reinstall.
4. Record what was posted (`celebration_posts`: team, kind, date, ts) so a
   restart or a second pod never posts twice. This avoids the in-memory job
   problem Connect follow-ups still have.

### Messages

Warm tone, short, Donut style. Names are mentions. No pronouns, since the
profile does not store them.

```
🎂 Today is @Priya's birthday!
Wishing you a lovely day, Priya. 💛
```

```
🎂 Today is a birthday double: @Priya and @Tom!
Wishing you both a lovely day. 💛
```

```
🎂 Tomorrow is @Priya's birthday!
Off for the weekend, so let's celebrate early. 🎈
```

```
🎂 On Monday it's @Priya's birthday!
It's a day off, so let's celebrate early. 🎈
```

```
🎉 Today is @Tom's 3-year work anniversary!
Thanks for three great years, Tom. 🙌
```

```
🎉 Today is @Tom's first work anniversary! 🥳
One year already. Thanks for everything, Tom.
```

Three or more people in one post list the names and use "Happy birthday to
all of you". Text is not customisable in the first version.

### Out of scope for the first version

- Weekly or monthly roundups (Donut has them; add if asked)
- GIFs or images
- Custom message text
- Manager mentions

## 8. Tests

- Profile: upsert validation, 29 February, no year stored from CSV, sync
  never overwrites a profile, `left_at` set on deactivate and cleared on
  reactivate, purge after 30 days.
- Celebrations: grouping, Friday covers the weekend, holiday on Monday posts Friday, Christmas run of holidays posts before it, Sunday to Thursday working week, opt-out respected,
  inactive members skipped, anniversaries under one year skipped, no double
  post after restart, timezone boundary at midnight.
- Dashboard: member can read and write only their own profile; admin can
  write any; CSV preview does not write.

## 9. Deliverables per release

### Release 1: Member profile

| Surface | Change |
|---|---|
| App | migration 051, `upsert_member_profile`, modal, App Home section, `/morgenruf profile`, dashboard My profile page, admin Members column and CSV import, leave and purge job, MCP read of profile fields |
| Docs | README profile section and Coming table, CHANGELOG, docs.morgenruf.dev profile page (fill in, CSV format, what happens on leave) |
| Website | privacy page (fields, no year, 30 day removal), `llms.txt` and `llms-full.txt`, homepage roadmap |

### Release 3: Celebrations

| Surface | Change |
|---|---|
| App | module (delegable to HR), settings page with timezone, working days and holiday list, daily job, `celebration_posts` table, core workspace calendar (`workspace_holidays`, working days), nudge DM, Ask for dates button, channel join prompt |
| Docs | README, CHANGELOG, docs.morgenruf.dev Celebrations page |
| Website | new `/celebrations` product page, Donut alternative and compare pages updated |

Intros (release 2) and Buddies (release 4) are specified separately.

The Celebrations release also deletes the stale `app/slack-manifest.yaml`
and `app/slack-manifest.json`; the root pair is the only manifest.

The website deploys only through the Netlify CLI; merging to main does not
deploy it.

## 10. Decisions (resolved 2026-09-27)

1. **Timezone** is a Celebrations setting chosen by HR, not shared with
   standup (section 7).
2. **Slash command** is `/morgenruf` with subcommands, so later features do
   not each need a new command:

   | Command | Does |
   |---|---|
   | `/morgenruf profile` | open your profile modal |
   | `/morgenruf help` | list what Morgenruf can do in this workspace |
   | `/morgenruf` (bare) | same as `help` |

   Later releases can add subcommands (for example `/morgenruf buddy` in
   Onboarding buddies) without a manifest change beyond the first.
3. **Holidays** are supported through a company holiday list that HR keeps
   (section 7). Celebrations on a holiday or non-working day post on the last
   working day before it.
