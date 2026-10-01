# Changelog

All notable changes to Morgenruf are documented here.
Format: [Keep a Changelog](https://keepachangelog.com) | Versioning: [SemVer](https://semver.org)

## [Unreleased]

## [1.9.14] - 2026-10-01

### Added
- **Polls.** `/morgenruf poll` opens a form, or
  `/morgenruf poll "Question" "Option 1" "Option 2"` posts one in the current
  channel. People vote with buttons on the message and the bars update live.
  Polls can be anonymous, allow more than one choice, hide results until they
  close, and close on their own. Anonymous votes are stored under a per-poll
  key that is deleted when the poll closes, so closed votes cannot be tied to
  anyone. There is a Polls page in the dashboard.
- **Pulse.** An optional weekly check-in by DM: how work was this week (1 to
  5), and eNPS every fourth week. Answers are kept only as counts, the list of
  who answered is deleted when a check-in closes, and results show only after
  it closes: averages from 5 answers, breakdown and eNPS from 10. Off by
  default; a workspace admin turns it on from the Pulse page.
- **Modules can add `/morgenruf` subcommands**, and are told when they are
  turned off so they can close what they have open.

### Changed
- The "one step left" DM after a quick start now also names the Slack menu
  path for adding Morgenruf to a channel, since `/invite` can open a menu.

## [1.9.13] - 2026-10-01

### Added
- **Quick start.** "Start a standup" in the welcome DM and on an empty Home
  tab opens a two-field form: the team's channel and a time. If Morgenruf is
  not in that channel yet, the standup is saved waiting for
  `/invite @Morgenruf` and switches on by itself when the invite happens,
  instead of refusing.
- **Day-2 nudge.** Two days after install, a workspace with no standup gets
  one DM to the installer with the same button. Once, never by email.
- **Monday usage report** to the operator alert channel: weekly active people
  and workspaces by stage. Internal workspaces are left out with
  `MORGENRUF_INTERNAL_TEAMS` (Helm: `ops.internalTeams`).
- **Install source.** `/install?ref=<source>` is stored on a new install and
  kept in workspace history.

### Fixed
- **A synced standup no longer falls back to the whole workspace.** When a
  channel-synced standup cannot read its channel, that run is skipped instead
  of DMing every known member.

## [1.9.12] - 2026-09-30

### Fixed
- **Removing the app deletes the workspace's data.** Workspaces whose Slack
  token stopped working (`account_inactive`, revoked tokens) were marked
  inactive but kept their members, answers and settings. A daily sweep now
  deletes that data 24 hours after removal, or 7 days after for
  `invalid_auth`, which can be a token problem on our side. It runs as a dry
  run that only logs what it would delete until `PURGE_INACTIVE_WORKSPACES=1`
  (Helm: `ops.purgeInactiveWorkspaces`).
- **Uninstall now deletes every table.** Nine tables with a team ID had no
  cascade and kept data after a normal uninstall, including Zoom tokens,
  standup threads, away and skip records, workflow rules and assistant keys.

### Added
- **Workspace history.** One row per workspace with dates and counts only (no
  names, emails, Slack IDs or message text), refreshed nightly and kept after
  removal, so it stays possible to see where teams stop during setup.

### Added
- **Workspace history.** A new `workspace_history` table keeps one row per
  workspace with counts and dates only: members, standups created, answers,
  kudos, delivered coffee matches, modules used, days installed. No user IDs,
  names, addresses or text. A nightly job refreshes it for every installation.

### Fixed
- **Removed workspaces have their data deleted.** Workspaces Slack reports as
  `account_inactive` or with a revoked token are purged 24 hours after they
  are retired, and `invalid_auth` after 7 days, since that can be a token
  refresh problem a reinstall fixes. A workspace that comes back is never
  purged. The sweep is a dry run that only logs what it would delete until
  `PURGE_INACTIVE_WORKSPACES=1` (Helm: `ops.purgeInactiveWorkspaces: true`).
- **Uninstall deletes everything.** The uninstall events relied on foreign key
  cascades, which missed Zoom links, standup threads, away and skip days,
  automation rules, module admins, MCP keys and install email records. The
  purge now deletes every table explicitly, records history first, and keeps
  only a bare installation row with its tokens cleared.

## [1.9.11] - 2026-09-30

### Security
- **OpenSSL is patched in the image.** The backend image now applies Debian
  security updates at build time, which picks up the OpenSSL fix for
  CVE-2026-75804 and CVE-2026-84782. The 1.9.10 tag failed its image scan on
  these and was never published, so 1.9.11 is the first release with the
  1.9.10 changes below.

## [1.9.10] - 2026-09-30

### Changed
- **Setup emails need an opt-in.** Installing Morgenruf no longer emails the
  installer. The welcome DM and the installer's Home tab offer an "Email me
  setup tips" button, and only after it is pressed does Morgenruf send the
  welcome email, the one-week check-in, the Sunday digest and the uninstall
  note to their Slack address. "Stop setup emails" on the Home tab turns them
  off, and every email carries an unsubscribe link. Emails reply to
  hello@morgenruf.dev.
- **The AI summary switch only shows when it can work.** The standup editor
  hides the AI provider and summary settings when the server has no OpenAI or
  Anthropic key, and the scheduler ignores the saved setting in that case.

## [1.9.9] - 2026-09-30

### Security
- **Kudos and AI summaries stay text.** A kudos reason, the kudos emoji or an
  AI summary could carry `@channel` or a disguised link into Slack. Both are
  now defused, and links show their real address.
- **People who leave lose access.** Dashboard sessions check once a minute
  that the member and the install are still active, and a deactivated
  installer is no longer an admin. Assistant (MCP) keys record who created
  them and stop working when that person is no longer an active admin. Keys
  made before this release keep working until revoked.
- **Members see only their own standups.** The standups list, reports and CSV
  export show standups a member is in or whose channel they can see. Emails
  and private channel membership are shown to admins only.
- **Workspace settings need a workspace admin.** The manager digest, AI
  settings and Jira URL can no longer be changed by a standup admin.
- **The public feed** only shows standups from public channels, and its token
  is created on the server and hidden from non-admins.
- **Zoom sign-in and email links are single purpose.** Zoom state is tied to
  the browser that started it, and each email link works only for what it was
  sent for.
- **Rate limits** on the public feed, email links, the sign-in callback and
  failed assistant key checks.

### Fixed
- **Streaks count.** They always showed 1. They now count your scheduled
  working days, skip holidays, and reset after a missed day.
- **The low participation rule** fired before every standup. It now checks at
  report time, and the `participation.low` and `blocker.detected` webhooks
  are sent.
- **Company holidays** skip the standup DM, reminder, nudge, report and coffee
  round.
- **"Until the report is posted"** now closes answers at report time. Before,
  it meant no limit.
- **Pausing, editing or deleting a standup from App Home** takes effect within
  about 15 seconds.
- **Reports use the dates you pick,** and analytics end on your team's local
  day.
- **A late answer is no longer lost.** A standup session lasts 20 hours.
- **Two reports racing** no longer leave an empty thread header behind.

### Changed
- Delivery failures are sent to the installer by DM instead of the channel.
- One help text everywhere, and `/morgenruf help` is the command to remember.
- The dashboard asks before destructive actions, offers undo on quick ones,
  and each empty page says what to do next.
- The API and assistant report the real app version.

## [1.9.8] - 2026-09-30

### Fixed
- **A blank or out-of-order standup answer is no longer saved.** Slack can
  deliver the Submit click before it has captured what was typed, and the
  blank was saved as the answer. The bot now asks you to submit again (send
  `pass` to leave a question blank on purpose). A Submit on a question already
  answered is ignored instead of being filed against the current one.
- **Dates and times follow your team's timezone.** App Home showed the time a
  standup was reported in UTC, the dashboard's Today page named the UTC date,
  and Insights called a standup filed today "yesterday" in the evening.
- **Today's next coffee chat matches the Coffee chats page.** It counted a week
  from a round run by hand, so a Monday programme showed a Tuesday.

## [1.9.7] - 2026-09-30

### Fixed
- **The web worker no longer shares database connections with the
  scheduler.** The connection pool was opened in gunicorn's master before
  the worker was forked, so a web request and a scheduled job could use one
  Postgres connection at the same time. It showed up as occasional failed
  webhook lookups, member updates and health checks ("no results to fetch").
  The worker now opens its own connections.

## [1.9.6] - 2026-09-29

### Fixed
- **Zoom meetings are booked only for the time a pair agrees.** A first tap on
  an offered time created the meeting, so if the pair then settled on another
  time (a suggested one, say), the meeting stayed at the first.
- **Standups are no longer delayed by long background work.** Coffee chat
  delivery, member sync and the other background jobs run on their own
  threads, so a standup cannot be dropped as missed while they run.
- **Two pods starting together no longer race on migrations.**

### Changed
- `LOG_FORMAT=json` writes one JSON object per log line, including gunicorn's
  access and error logs. The chart sets it by default.
- Helm chart 0.14.0: a startup probe, seccomp, a read-only root filesystem
  (toggle `readOnlyRootFilesystem`), image digest pinning, and an optional
  PodDisruptionBudget for more than one replica.
- The image scan now fails the build on fixable critical or high findings.
- An operator runbook, `RUNBOOK.md`.

## [1.9.5] - 2026-09-29

### Security
- **Signing in no longer makes a member an admin.** Dashboard sign-in runs
  through the install flow, and finishing it granted admin to anyone. Admin
  now goes only to the person who first installed the app and to Slack's own
  workspace admins and owners.
- **The sign-in link works once** and only in the browser that started it.
- **Webhooks cannot reach internal addresses.** The target is resolved when
  it is sent, private addresses are refused, and redirects are not followed.
- **`LOG_LEVEL=DEBUG` is only a log level.** It no longer starts Flask's debug
  server, and Slack tokens are never written to the logs.
- **Standup answers stay text.** Typing `@channel` or a disguised link into an
  answer no longer pings the channel or renders the link.
- **Creating, editing, pausing and deleting standups from App Home** needs the
  standup admin role, the same rule as the dashboard.

### Fixed
- **Reports and nudges use your team's own date.** They used the server's UTC
  date, so teams far from UTC (Sydney, or US teams reporting late in the day)
  got empty reports and nudges after they had already answered.
- **The weekend reminder** went to every member of the workspace. It now goes
  to the standup's participants.
- **A coffee round interrupted partway through delivery now finishes** instead
  of leaving the remaining pairs without an introduction, and a rate limited
  Slack no longer drops a pair.
- **A brief database error no longer removes a workspace's coffee chat and
  celebration jobs.**
- **Assistant (MCP) queries are limited to a year of history.**

### Changed
- `/healthz` checks the database and the scheduler and returns 503 when
  either is down. `/livez` checks only the scheduler, for liveness probes.
- The operator is alerted in Slack when a scheduled job fails or misses its time.

## [1.9.4] - 2026-09-29

### Added
- **Suggest another time for a coffee chat.** The introduction offers a few
  times, and until now there was no way to propose a different one. A
  "Suggest another time" button opens a date and time picker in your own
  timezone; the suggestion is posted to the group DM in everyone's local time
  with a "Works for me" button, and it settles the same way as the offered
  times, with a calendar link and the meeting room.

## [1.9.3] - 2026-09-29

### Fixed
- **Standups with an old timezone name now run.** Chrome reports some zones by
  their old names (Asia/Calcutta for India), and the server image could not
  resolve them, so a schedule saved that way never fired. The server now ships
  its own tz database, timezones are saved under their current names, and
  migration 057 rewrites old names already stored.
- **One broken schedule no longer blocks the others.** Startup and the two
  minute schedule sync registered every schedule in one loop, so a row that
  failed stopped every row after it. Each schedule and workspace now registers
  on its own, and a failing one is logged and retried.

## [1.9.2] - 2026-09-29

### Fixed
- **Scheduled jobs are no longer dropped when two are due at once.** A job
  that started more than a second late was skipped as missed, and claiming
  each firing in the database made the second of two simultaneous jobs start
  late. A standup report was lost this way. Jobs now run if they start within
  five minutes.
- **Coffee chat rounds use a current Slack token.** Round and Kudos jobs kept
  the bot token from when the server started, and tokens rotate every 12
  hours, so a round a week later failed on an expired token. The token is now
  read when the job runs.
- **Changing a coffee chat programme's day or time takes effect right away.**
  The old schedule kept firing until the next restart.
- **A missed coffee chat round starts later the same day.** If the weekly
  firing is missed (server down, token error), a five minute check starts
  the round once its time has passed, on the programme's own weekday only.

## [1.9.1] - 2026-09-28

### Changed
- **Sidebar icons have colours.** Each feature keeps its own icon colour
  (Standups blue, Coffee chats amber, Kudos rose, Celebrations violet and so
  on), in light and dark mode. Labels stay neutral.
- **My profile shows your Slack name and photo** above the form.

### Fixed
- **A report date far in the past no longer restarts the server.** Typing a
  year into the Reports date picker sends 0002, 0020 and 0202 on the way to
  2026, and each asked for hundreds of thousands of days of participation,
  which ran the backend out of memory. Report and participation windows are now
  capped at a year, the same cap the analytics endpoint already had.
- **No duplicate standups, reports or reminders during a deploy.** Each pod
  runs its own scheduler, and while the old and new pods overlapped both
  fired anything due in that minute. Every cron firing is now claimed in the
  database first (migration 056) and runs on one pod only. Claims older than
  a week are removed nightly.

## [1.9.0] - 2026-09-28

### Added
- **Member profiles.** Each person can keep a birthday, start date, role,
  location and "ask me about" in Morgenruf, from a new "Your profile"
  section on the Slack App Home, with `/morgenruf profile`, or on a new
  **My profile** page in the dashboard. Birthdays are day and month only;
  no year is ever stored. Intros, Celebrations and Onboarding buddies will
  read this profile.
- **Admins can fill in dates for the whole workspace.** The Members page
  shows each person's profile, lets a workspace admin edit it, and imports
  `email,birthday,start_date` from a CSV. The import previews matched,
  unmatched and invalid rows before saving anything, drops the year from a
  full birthday date, and leaves profiles people wrote themselves alone
  unless "Overwrite entries members made themselves" is ticked.
- **Profiles are removed when someone leaves.** When the Slack sync sees a
  person has gone, their profile is marked and deleted 30 days later by a
  nightly job. Returning within 30 days keeps it.
- `get_member_profiles` MCP tool, read only.
- **Celebrations.** Birthdays and work anniversaries are posted in a
  channel you choose, one message per kind per day, with a 🎉 from the
  bot. Off by default; a workspace admin turns it on once a channel and a
  timezone are set. It has its own timezone and post time (09:00 by
  default), separate from standups. A start date less than a year ago is
  skipped, 29 February birthdays are celebrated on 28 February in other
  years, and nobody who opted out or has left is posted. Each post is
  recorded before it is sent, so a restart or a second pod never posts it
  twice, and a pod that was down at post time catches up within a few
  hours.
- **Working days and company holidays.** Set the working week (Monday to
  Friday by default) and keep a holiday list, added one by one or
  imported as `date,name` with a preview first. A celebration on a
  weekend or a holiday is posted on the last working day before it
  ("Tomorrow is...", "On Sunday it's...", "On 25 December it's...").
  The calendar belongs to the workspace, so later features can plan
  around it too. Holidays more than a year old are removed nightly.
- **Asking people for their dates.** With Celebrations on, everyone with
  no birthday and no start date gets one DM asking for them, with "Add my
  dates" (opens the profile form) and "Skip me" (no public celebration).
  "Ask for dates" on the Celebrations and Members pages sends it again,
  at most once per person every 30 days, after showing the count and the
  message. Joining the celebrations channel asks too.
- A **Celebrations admin** grant, so HR can run celebrations, working days
  and holidays without being a workspace admin.

### Changed
- Dependencies: slack-bolt 1.30.0, pyjwt 2.15.0, posthog 7.60.0, pytz 2026.4,
  vite 8.3.1, @tanstack/react-query 5.103.2, @testing-library/jest-dom 7.0.1,
  typescript-eslint 8.70.1, @types/node 26.6.2, github/codeql-action 4.38.2.
- `/morgenruf` now has subcommands: `/morgenruf profile` opens your profile
  and `/morgenruf help` (or `/morgenruf` alone) lists what Morgenruf can do
  in your workspace, based on which features are switched on. `/help`,
  `/standup`, `/skip` and `/kudos` are unchanged. Self-hosted installs:
  update the `/morgenruf` entry from `slack-manifest.yaml` to get the new
  usage hint in Slack; the command works without it.
- The app asks for one new Slack scope, `reactions:write`, for the 🎉 on
  Celebrations posts. Existing workspaces keep working without it and get
  the reaction after re-authorising. Self-hosted installs: add it to your
  Slack app from `slack-manifest.yaml`.

### Fixed
- **The coffee chat welcome is sent when someone joins a programme's
  channel.** Slack events reach only the first listener registered for
  them, and standup's welcome was registered first, so the coffee chat one
  never ran. One listener now offers each channel join to every feature;
  standup's welcome is unchanged.
- **The standup welcome DM is sent only for a standup channel.** Joining
  any channel the bot was in (the celebrations channel, a coffee chat
  channel, or any other) sent "Welcome to the team! I'm Morgenruf, your
  daily standup bot". It now goes only to someone joining a channel with an
  active standup in that workspace.

## [1.8.16] - 2026-09-28

### Fixed
- **The install alert says who installed and where.** It mentioned the
  installer as `<@U...>`, which only resolves inside the installing workspace,
  so the operator saw an empty name. The alert now looks up the workspace
  domain and the installer's name, email, title, timezone and admin status
  with the new install's bot token, writes them as plain text with the ids,
  and counts only active workspaces. A lookup that fails leaves that detail
  out and the alert still goes.

## [1.8.15] - 2026-09-28

### Fixed
- **Kudos are saved again, from both `/kudos` and a DM.** No kudos had ever
  reached the database. `/kudos` and `/morgenruf-kudos` were declared without
  `should_escape`, so Slack sent `@Anmol Nagpal` as plain text, the handler
  found nobody, saved nothing, and still showed a "wants to recognise someone"
  card. Both commands now ask Slack to escape mentions, `<@U123>` and
  `<@U123|name>` are both understood, and a plain `@name` is matched against
  the workspace roster when exactly one person has that display or real name.
  When nobody can be found the giver gets a short usage hint instead of a
  card. `kudos @someone ...` sent by DM never ran at all: Bolt runs only the
  first listener that matches an event, and core's DM listener is registered
  before every module, so kudos' own listener was never reached. Kudos now
  takes its DM through the core DM router, ahead of standup's answer
  collection, which is otherwise unchanged. The slash command now applies the
  same self-kudos and daily allowance checks as the DM, and a kudos that fails
  to save says so instead of posting a card. Hosted installs need "Escape
  channels, users, and links" ticked for both commands in the Slack app
  config.
- **Standup's DM keywords work.** `help`, `standup`, `skip`, `I'm away`,
  `I'm back` and `timezone <tz>` never ran in production, even though the
  welcome DM says "Type `help`" and App Home advertises `standup`, `skip` and
  `I'm away`. Their listeners were registered after core's catch-all DM
  listener, and Bolt runs only the first listener that matches. They now go
  through the core DM router like kudos, and only a message that is the whole
  keyword counts (any case, trailing punctuation ignored), so an answer such
  as "need help with the deploy" is still an answer. While a standup is being
  answered, `skip` stays an answer, `pass` leaves the question blank as the
  standup DM always promised, `help` shows help without using up the answer,
  `standup` says one is already in progress instead of restarting it, and
  `I'm away` closes the open standup like the **I'm away** button. App Home's
  help no longer lists an `edit` keyword that never existed, and the vacation
  banner asks for `I'm back` rather than "just send me a message".
- **The person you give kudos to is told.** The kudos card only went to
  the legacy workspace channel, which nothing in the dashboard or the API
  sets, so in current workspaces only the giver saw it. Every kudos that is
  saved now sends the recipient a DM with who it is from and why. Nothing is
  sent for a kudos that was refused or failed to save. The giver's reply says
  where it went ("Sent to @x", or "Sent to @x and posted in #kudos"), and says
  so when a DM or the channel post could not be delivered.
- **Empty channel pickers explain themselves.** When the bot is in no channel yet, every dashboard channel picker says to `/invite @Morgenruf` and offers a Refresh channels button.
- **Participation only counts days a standup existed.** Days before a schedule was created are no longer expected, and a rate built on fewer than five expected answers reads "Too early to judge" instead of "Needs a look".
- **Insights no longer says "Everyone has been recognised" with zero kudos.** Every contributor without kudos is listed, and a workspace with no standups gets a neutral "No standups yet" state.
- **App Home shows the report time.** Cards said "Reports at" the standup time; they now show the report time (or the default an hour later), naming the standup's timezone when it differs from the reader's.
- **The Slack manifests agree on the interactivity URL.** `slack-manifest.yaml` now uses `/slack/interactions` like the JSON, and the unused copies in `app/` are gone.

### Added
- **A kudos channel.** Kudos has a channel setting of its own (migration
  055), on the Kudos page next to the token and daily allowance and in
  `/dashboard/api/kudos/config`. The list shows only channels Morgenruf is in,
  and says "Invite @Morgenruf to a channel first" when there are none. The
  card is posted there when it is set, falls back to the legacy workspace
  channel when that is set, and otherwise only the DMs go out. A save that
  leaves the channel out keeps the one already chosen. The same people who can
  change the token can change the channel: workspace admins and anyone with
  the kudos grant.

## [1.8.14] - 2026-09-28

### Fixed
- **Coffee chats now send the day 3 nudge and the day 6 "did you meet?"
  question.** Both were queued as one-off jobs on the in-memory scheduler, and
  the module job sync that runs every two minutes removed them as jobs no
  module had asked for, so no round was ever nudged or closed. A restart would
  have lost them too. They are now stored in the database (migration 052) and
  a sweep every five minutes sends what is due, safely with more than one pod
  running. Rounds left open by the old behaviour are picked up on the first
  sweep after deploy: a follow-up that is still recent is sent, a nudge more
  than a day late or a closing question more than three days late is skipped,
  and a round whose closing question is skipped is marked closed without
  messaging anyone.
- **The Helm chart stays on Postgres 16.** A dependency bump had moved the
  bundled database to Postgres 18, which cannot start on a Postgres 16 data
  directory and keeps its data in a different path, so `helm upgrade` would
  have broken existing installs. Moving to 18 needs a planned upgrade and
  will come separately.

## [1.8.13] - 2026-09-27

### Fixed
- **A workspace that revoked Morgenruf is no longer retried every minute.**
  When the pre-standup token check failed, the run re-queued itself in 60
  seconds with no limit, so a revoked workspace was retried hundreds of times
  an hour until the pod restarted. Errors no retry can fix (token revoked,
  workspace inactive or disabled) now skip that run with one warning, and
  anything else is retried three times, after one, five and fifteen minutes.

## [1.8.12] - 2026-09-27

### Fixed
- **Removing someone from a standup in the dashboard now sticks.** A standup
  created from Slack with "sync with channel" on replaces its participants
  with the channel's members before every run, and the dashboard never showed
  that setting, so a removed person came back the next morning. The editor now
  has a "Sync with channel members" checkbox; while it is on, the participant
  picker is hidden. Turn it off to choose people yourself.

### Changed
- Dependency updates: psycopg2-binary 2.9.13, posthog 7.59.0, resend 2.47.0,
  sentry-sdk 2.70.0, marshmallow 4.3.1, frontend build image node 26-alpine.

## [1.8.11] - 2026-09-24

### Added
- **The dashboard shows when each coffee chat runs next.** Programme cards read
  "Next round: Monday, 28 September", worked out the same way as the scheduler
  and the Slack App Home, so the three always agree. A pinned date is marked,
  and a paused programme shows none.

### Fixed
- A pinned next round date no longer shows a day early for timezones west of
  UTC.

## [1.8.10] - 2026-09-24

### Fixed
- **Coffee chats no longer skip a week after "Run now".** The schedule counted
  from the latest round of any kind, so trying a Monday programme by hand on a
  Thursday made the following Monday "not due". Manual rounds are now extras:
  the regular round still runs, and a pinned next date stays in place.
- The next coffee chat date shown in Slack always falls on the programme's own
  weekday and respects a pinned date.
- Clicking "Run now" twice on the same day no longer sends a second set of
  introductions. The check uses the programme's timezone.

### Changed
- Migration `050_connect_manual_rounds.sql` adds `connect_rounds.manual`.
  Additive, with a default, so rollback is a plain image revert.

## [1.8.9] - 2026-09-24

### Changed
- **Dashboard routing runs on TanStack Start in SPA mode.** Pages load their
  data before they render, filters live in the URL so bookmarks and refreshes
  keep them, and malformed links recover instead of erroring. The frontend
  image now serves `_shell.html` as its entry point; Nginx routing is otherwise
  unchanged.

### Fixed
- Search boxes on Members and Standups keep every keystroke while the session
  refreshes in the background.
- Report date filters no longer drop digits while the page refreshes.
- Logging out lands on the plain login page instead of sometimes redirecting
  back with a `next` link to the page you just left.

## [1.8.8] - 2026-09-20

### Added
- **A sidebar and scroll areas that hold their shape.** The dashboard moved to a
  shadcn sidebar with consistent scrolling, so long member and participant
  lists no longer stretch the page. Loading states now cross-fade rather than
  snapping, and respect `prefers-reduced-motion`.
- **Charts rebuilt on EvilCharts.** Analytics and attendance render through a
  vendored Recharts layer, with a data table behind every chart for anyone who
  wants the numbers instead of the picture. Chart bundles stay split per page.
- **Timezone selects and compact member actions.** Picking a timezone is a
  search rather than a long list, and member rows fit more without wrapping.

### Fixed
- Report filters survive consecutive edits instead of resetting between saves.
- Settings toggles are switches, so their state reads at a glance.
- Page headings reserve space for their call to action, so titles stop shifting
  as buttons load.
- The standup status badge no longer crowds the edit link.

### Changed
- Browser tests allow 90s per case. The chart matrix renders a full analytics
  page per viewport, theme and motion preference, and the slowest runs for
  about 40s. The previous 30s default only passed in CI because the retry
  hid it.

## [1.8.7] - 2026-09-20

### Added
- **The dashboard ships as its own service.** The browser application moved to a
  React build served by its own `morgenruf-frontend` image, which proxies API
  and integration requests to the backend. Pin both `image.tag` and
  `frontend.image.tag` to the same release and upgrade them together. The
  `morgenruf` service keeps its name and port and now fronts the frontend, so
  an existing ingress or tunnel needs no change and starts serving the new
  dashboard on upgrade. The backend moved to `morgenruf-backend` for anything
  that addresses it directly.

### Fixed
- **Each kudos leaderboard announces itself.** The Most recognized and Most
  encouraging columns both labelled their loading state "Loading leaderboard…",
  which put two identical live regions on the page and made screen readers
  announce it twice. Each column now carries its own label.

### Changed
- Dependency updates: gunicorn 26.2.0, slack-sdk 3.44.1, sentry-sdk 2.69.2,
  PyJWT 2.14.0, pytz 2026.3.post1, and the frontend image now builds on
  Node 25.

## [1.8.6] - 2026-09-20

### Added
- **Product analytics, off unless an operator switches them on.** `POSTHOG_API_KEY`
  turns on workspace-level counting: installs, uninstalls, standups posted,
  coffee matches, kudos and module toggles. The distinct ID is the Slack team
  ID, and no Slack user ID, channel name or standup text is ever sent.
  `POSTHOG_HOST` defaults to the US cloud. Unset means nothing leaves the
  instance, which is what a self-hosted install gets.

## [1.8.5] - 2026-09-18

### Added
- **Consent is recorded rather than assumed.** The welcome email now carries an
  opt-in block that says plainly that nobody is subscribed to anything yet.
  Clicking it validates an HMAC token, writes the grant with its source and IP
  address, and syncs the contact to a Resend audience. Unsubscribing reverses
  both halves. The `email_consents` table is the record CASL asks for, and the
  copy every downstream list gets rebuilt from.
- **A farewell email when a workspace leaves.** Eleven of the first twenty
  installs removed the app without ever running a standup, and not one said
  why. The message confirms the data is gone, shows how long they had it and
  how many standups they ran, asks one question, and does not argue. It runs
  before the delete, because the address and the history it needs are in the
  rows about to be removed.
- **An operator alert when a workspace arrives or leaves.** `MORGENRUF_ALERT_WEBHOOK`
  takes a Slack incoming webhook in the operator's own workspace. The install
  alert carries the running workspace count, the uninstall alert carries the
  days installed and standups run. Unset means silence, which is the right
  default for a self-hosted install.
- **Bounce and spam-complaint handling.** `/webhooks/resend` accepts Resend's
  Svix-signed deliveries, verified with HMAC-SHA256 in constant time inside a
  five-minute window, and checking every signature in the header so a secret
  rotation does not drop events. A bounce or a complaint alerts the operator
  and suppresses the address locally, which is the list the send path actually
  consults. Opens and clicks are deliberately ignored.

### Changed
- `RESEND_AUDIENCE_ID` and `RESEND_WEBHOOK_SECRET` are both optional. Without
  them, consent is still recorded locally and nothing is sent anywhere.

## [1.8.4] — 2026-09-18

### Fixed
- **The Members page offered grants for two features with nothing to
  administer.** Insights only reads and MCP keys are workspace-wide, so either
  grant sat in the table and changed nothing while the card showed a switch
  that looked live. A module now declares whether it can be delegated.

### Changed
- The README shows the product: four screenshots, one badge row, and a quick
  start that leads with Helm and Docker Compose.

## [1.8.3] — 2026-09-18

### Fixed
- **A standup dialog reopened on whatever tab it was left on.** Panes are
  toggled in place, so leaving it on Advanced and pressing Edit again showed
  Advanced: one collapsed accordion and none of the fields somebody came back
  for. Both openers start on Basics now.

## [1.8.2] — 2026-09-18

### Fixed
- **The coffee chat member table showed Slack ids instead of names.** Every
  row read U06CRLYF72L with no face. The table asked each person for
  `real_name` and `avatar`, and the roster record carries neither: the field
  is `name`, and there was no picture on it at all. Both silently became empty
  strings, so the name fell back to the id. Present since that table shipped.
  The roster record now carries the name and the picture, falling back to the
  Slack handle.

### Changed
- The coffee chat settings preview moves below the controls at 1080px rather
  than 900px, so the form is not squeezed into half a narrow window, and every
  modal is capped by the window as well as by its own maximum.

## [1.8.1] — 2026-09-18

### Fixed
- **Every modal and every toast was invisible.** The coffee chat settings
  modal never closed its body, so the forty-eight elements after it in the
  file became its children, including the create/edit standup modal, the new
  coffee chat modal and the toast container. That parent is hidden until the
  settings modal opens, so pressing Edit on a standup did nothing, New
  Standup did nothing, New coffee chat did nothing, and no action ever
  confirmed itself. Shipped in 1.8.0.
- **The coffee chat sub-navigation bounced back to Standups.** Every sidebar
  row was bound to its own section, and the three sub-items name none, so each
  click opened Coffee chats and was immediately sent back to the fallback.

## [1.8.0] — 2026-09-18

### Added
- **Per-feature admins.** Roles were workspace-wide and binary, so putting a
  team lead in charge of the standups meant handing them webhooks, API keys
  and the public feed as well. A grant is now one row per person per feature:
  the lead runs standups, someone else runs coffee chats and kudos, and
  neither can mint a key or publish the workspace's standups. A workspace
  admin still implies every feature, so no existing permission changed.
- **Coffee chats settle on a time.** A pairing proposes slots in both people's
  working hours, they vote, and the winning slot becomes the meeting. With
  Zoom linked, the meeting is created at the agreed time.
- **Zoom account linking**, group sizes from 2 to 8, re-match requests,
  opt-out and snooze, and a coffee chat settings page with a live preview of
  the Slack message.
- **Standup nudge.** Whoever has not filed by report time gets a private
  reminder.
- **Per-standup digest email**, replacing the single workspace-wide address.
- **A standup's health on its card**: fourteen days of completion as a
  sparkline, with a badge when it starts slipping.
- **Feature switches in Settings**, and an icon per page.

### Fixed
- **A plain member could publish the workspace's standups and mint an API
  key.** Fourteen mutating routes had no role check, including deleting a
  standup and rotating a webhook secret.
- **A workspace could lock itself out of its own settings permanently.**
  Demoting the last admin left nobody who could promote anyone. Thirteen of
  twenty workspaces had exactly one admin.
- **No workspace-level setting could ever be saved.** The upsert named a
  conflict target with no matching constraint, so every write raised since
  the feature shipped.
- **Settings that saved and did nothing**: report channel, AI provider,
  video mode, nudge-on-skip, and ten fields the schedule form discarded on
  the way to the server.
- **Turning the standup nudge on did nothing until a restart.** The job
  reconciler compared triggers without the nudge fields, so it never noticed
  the change.
- **A coffee chat round that did not run was advertised as still coming**, and
  a programme that had never run was reported as due today whatever day it
  was.
- **Zoom could not be switched on by any Helm install**: the credentials were
  read by the code and never passed by the chart.

### Removed
- Twenty automation rules that had no effect, ten orphaned settings columns,
  and a column added and never read in the same week.

## [1.7.5] — 2026-09-17

### Fixed
- **A module that defaults to off could never be turned on.** The workspace
  toggle had no control anywhere: the API endpoint existed, was well-formed,
  and had no caller. A workspace that granted the Connect scopes landed on a
  Coffee chats page that looked ready, with a programme listed, and nothing
  would ever run, because scheduled jobs are only planned for active modules.

## [1.7.4] — 2026-09-17

### Added
- **Coffee chat programmes can be edited.** They could be created and deleted
  but never changed, so altering a time meant deleting the programme and losing
  its round history with it.
- **Meeting options**: a room the whole programme shares, and a chat length.
  Both appear in the introduction, so finding somewhere to meet is no longer
  left entirely to the pair.
- **Proposed times with calendar links.** Where two people's working days
  overlap, the introduction offers hours that suit both, each opening Google
  Calendar with the event filled in. The message says plainly that no calendars
  were checked: without calendar access we can say an hour suits their zones,
  never that they are free.
- **Run a round now**, so a programme can be tried before its scheduled day.
- **Snooze for two weeks** from the App Home. `paused_until` had been in the
  schema and honoured by the eligibility query since the table existed, and
  nothing ever wrote one.
- **Working-hours matching**, off by default. A nine-to-five in Toronto and one
  in Kolkata share no hours at all, so enforcing it everywhere would quietly
  stop matching the teams that most need introducing.

## [1.7.3] — 2026-09-17

### Added
- **Coffee chats on the Slack App Home.** When your next introduction is, and a
  way to pause and resume yourself. The only way to pause had been a button on
  a round message, which is no use between rounds.
- **A welcome when you join a coffee chat channel**, naming the cadence and the
  date of the next introduction. Slack shows nothing about a bot's schedule, so
  people joined and waited without knowing anything was coming.
- **A digest per standup.** The workspace-level one sends every standup to a
  single address, so a workspace running several could not give each team's
  lead their own team's answers. Each standup can now name its own recipient.
- **Starter templates on the Automation page**, covering what the existing
  triggers and actions were built for. Picking one fills the form and saves
  nothing.

### Fixed
- **The mcp 2.x bump broke the stdio MCP server** and no test noticed, because
  nothing imported it. Rewritten on the new API, and it now builds its tools
  from the HTTP endpoint rather than keeping a second list that had drifted.
- **"Next coffee chat: today"** on any day, for a programme that had never run.
  It ignored the programme's own weekday.
- **"No standups yet" above a list of ten standups**, for an admin who takes
  part in none of them.
- **Ten stacked Configure buttons** on the App Home, costing two blocks each
  against the hundred a Slack view may contain.
- **The Slack preview rendered `:morgenruf:` as literal text** in the one panel
  whose job is showing what Slack shows.
- **Coffee chats had no timezone control**, and the picker it eventually got
  was a native datalist four hundred entries deep spilling out of the modal.
  One picker component serves both forms now.
- **Editing the kudos allowance switched off the branded token**, because the
  settings form submits every field and any save counted as choosing a token.
- **The coffee chat pool counted the whole workspace** rather than the channel.
- Twenty-odd names on the Today page were rendered as full-size pills.

## [1.7.2] — 2026-09-16

### Fixed
- **Editing the kudos allowance switched off the branded token.** The settings
  form submits every field, and any save was treated as the admin choosing a
  token, so changing the allowance silently opted a workspace out of the emoji
  it had just imported. Automation now stops only when the token changes.
- **The token field was sized for a single character**, so a shortcode such as
  `:morgenruf:` overflowed and read as broken. It fits now, beside a preview of
  what Slack will actually render.
- **The coffee chat pool counted the whole workspace**, so a channel with two
  people in it advertised twenty-three. The round itself was always correct;
  only the number was wrong.
- **Coffee chats had no timezone control** and silently used the browser's.
- `schedule_days` parsing no longer leaves braces on the first and last day
  when the column holds a Postgres array literal.

## [1.7.1] — 2026-09-16

### Fixed
- **Coffee chats could never be enabled.** The scopes the module requires were
  never requested: `mpim:write`, `mpim:history` and `users.profile:read`
  appeared nowhere except its own declaration, so the dashboard reported them
  missing, the re-authorise button asked Slack for the same scopes as before,
  and the workspace landed back on the same screen. Adds them to the install
  URL and both manifests, and a guard asserting that every module's required
  scopes are actually requested.
- **Insights showed names without faces.** The avatar component was written for
  the coffee chat attendance rows and named for them, so no other page could
  use it.

> Updating the Slack app's own manifest at api.slack.com is a separate step:
> the file in this repository is not live configuration, and Slack refuses an
> install that requests scopes the app does not declare.

## [1.7.0] — 2026-09-16

Morgenruf becomes four modules over one deployment and one database. Standups
are unchanged; coffee chats, kudos and insights sit alongside them, and each
can be switched off without touching the others.

### Added
- **Coffee chats.** Pairings from a channel on a cadence, history-aware so the
  same two people are not matched twice running. Odd numbers form one group of
  three so nobody sits out. The bot nudges pairs who have not met and asks
  whether they did. Off until enabled: it needs `mpim:write`, `mpim:history`
  and `users.profile:read`, so an existing workspace must re-authorise.
- **Attendance**, reported four ways rather than two. "Not met" hides three
  different situations: they said no, they never answered, or the invite never
  reached them. Only the last is a delivery failure, and folding it into "did
  not meet" blames people for it.
- **Kudos allowance**, resetting at midnight in each person's own timezone,
  with leaderboards for who is recognised and for who does the recognising.
- **Insights**: a blocker nobody has cleared in days, someone who answers every
  standup and is thanked by nobody. Neither is visible in one dataset alone.
- **MCP goes from 8 tools to 17.** Modules contribute their own, and the tool
  list runs the same activation gates as the dashboard, so a workspace is never
  offered a tool for a feature it has not enabled.
- Slack profile pictures and handles on the roster, and a Today overview page.

### Fixed
- **A workspace could read another workspace's coffee chat rounds.** The rounds
  route never read the session's team, and its query had no team filter, so any
  signed-in user could page through another workspace's history by guessing a
  programme id. Unexploited: nothing called it yet.
- **The bundled PostgreSQL could not start at all.** `postgresql.enabled=true`
  pulled `bitnami/postgresql:16`, which Docker Hub now returns 404 for. It is a
  StatefulSet running the official image now, which is what production has
  always used. Also fixes values.yaml claiming the password was auto-generated
  when nothing generated it.
- **A large standup summary posted nothing at all.** Slack rejects messages
  over 50 blocks.
- **Light theme**: six colours left hardcoded from the dark-only era, including
  kudos mentions at 2.98:1 and a lavender-on-lavender sidebar item.
- **A dead Slack avatar URL showed a broken image on every row.** They 404 as
  soon as someone changes their profile picture.
- **Reports ran to thirty screens** at a hundred people. It paged by day, but a
  day is a hundred rows at that size.

## [1.6.0] — 2026-09-03

A scheduled standup could fire perfectly and still look completely broken. Four
separate faults made the difference invisible, and together they produced a
support report of "I set a time and nothing happened" for a workspace whose
standup had in fact run on time and delivered every DM.

### Fixed
- **The daily channel summary could not be turned on by anyone** (#117). Migration
  021 defaulted `post_summary` to `FALSE` and promised a dashboard control to
  re-enable it; that control was never built, so `post_summary` appeared in no
  Slack modal and no dashboard markup, and every schedule in every install had
  the roll-up permanently off. The toggle now exists in both places, new
  standups default to posting, and migration 028 restores the column default.
- **The report job ran in the same second as the standup DMs** (#118). With no
  explicit `report_time` the fallback was `schedule_time` itself, putting both
  jobs on the same cron minute. The report therefore found nothing in
  `standups` and skipped, every single day. It now defaults to an hour after
  the standup.
- **The timezone picker silently substituted UTC** (#121). It offered 63 curated
  zones; anyone whose Slack timezone was one of the other 370 could not select
  it, could not search for it, and was quietly preselected UTC on a required,
  prefilled field. Every valid zone is now selectable, a real zone preselects
  as itself, and when no usable zone is known the field forces a deliberate
  choice instead of letting UTC pass as one. Timezone aliases (`ist`, `pst`)
  now rank first in the dropdown.

### Changed
- The Slack modal field that sets the DM time was labelled "Report time", so
  people set it believing it controlled when the summary posts. It is now
  **Standup time**, and the report time is its own optional input defaulting an
  hour later. A modal opened before this change still submits correctly.
- Saving a standup now DMs its creator with the channel, standup time,
  timezone, active days, participant count and next run, and **warns when the
  creator is not on the participant list** — the case that produced the
  original report. It also explains that answers reach the channel through the
  DM, so a quiet channel is accounted for rather than mysterious.

### Added
- Next run time on the App Home standup list and the dashboard standup cards,
  derived from each schedule's own cron trigger so it reads the same in the
  dashboard's forked worker as in the process holding the live jobs.

### Notes for upgraders
- Migration 028 changes only the `post_summary` **column default**. Existing
  schedules keep whatever value they hold. Some were set to `FALSE` by
  migration 021 rather than by their owner, but flipping them on automatically
  would start posting to live channels unannounced, so that stays the owner's
  call via the new toggle.
- Schedules with no `report_time` will see their report job move one hour
  later. With `post_summary` off, which is every pre-upgrade schedule, this
  changes nothing visible.

## [1.0.0] — 2026-04-05 🎉 First stable release

### Added
- 🔐 Full OAuth 2.0 install flow with persistent token store
- 📊 Web dashboard (React) — manage standups, schedules, team settings
- 🤖 MCP server at `/mcp` — connect Claude, Cursor, Copilot directly
- 📡 Public status page at [status.morgenruf.dev](https://status.morgenruf.dev) with live service health checks
- 📖 Full documentation site at [docs.morgenruf.dev](https://docs.morgenruf.dev)
- 🧪 80-test Playwright E2E suite (smoke + full) running on every push
- 🔄 Dependabot enabled for pip, Docker, GitHub Actions, Helm

### Infrastructure
- Kubernetes (k3s) production deployment with Helm chart
- Cloudflare-proxied custom domains with enforced HTTPS
- GitHub Actions CI/CD: Docker build → DockerHub push → k8s rollout
- Netlify-hosted marketing website

### Fixed
- Status page HTTPS certificate provisioned (Cloudflare DNS-only mode)
- Dashboard 302 redirect now correctly reported as "operational" in health checks
- Microsoft Teams icon CDN 404 (cdn.simpleicons.org removed the slug)
- Dependabot config not activating (`.yaml` → `.yml` rename)
- Node.js 20 deprecation warnings in CI (upgraded to Node.js 22)

## [0.4.0] — 2026-04-05
### Added
- ⚡ Workflow automation rules engine (blocker/participation triggers → post/DM/webhook)
- 🏆 Kudos / peer recognition system with leaderboard
- 🔐 Role-based access control (admin/member)
- 🤖 AI standup summary (OpenAI GPT-4o-mini / Anthropic Claude Haiku)
- 📅 Multiple standup schedules per workspace
- 📝 25 pre-built question templates
- 🔗 Jira / GitHub / Linear auto-linking in summaries
- 🌐 Google Chat adapter (Beta)
- 🔧 MCP server for AI assistant integration (Claude, Cursor, Copilot)
- 📊 Public standup feed URL (shareable read-only page)
- 📧 Manager digest email (daily HTML summary)
- 🛡️ Redis-backed sessions (survives pod restarts)
- 🚨 Sentry error monitoring

## [0.3.0] — 2026-03-20
### Added
- 🏠 Slack App Home tab
- ⏭️ Skip today command
- ⏰ Reminder notifications
- 🌍 Per-user timezone support
- 📈 Analytics dashboard with participation charts
- 📤 CSV export
- 😊 Mood tracking
- 📬 Weekly digest

## [0.2.0] — 2026-03-01
### Added
- 🌐 Web dashboard for workspace configuration
- 🔗 Webhook integrations
- ✏️ Edit window for standup responses
- 📧 Welcome email on install

## [0.1.0] — 2026-02-15
### Added
- Initial release
- Slack OAuth install flow
- Daily standup DM flow (3 questions)
- Standup summary posted to channel
- PostgreSQL persistence
- Helm chart

[Unreleased]: https://github.com/morgenruf/morgenruf/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/morgenruf/morgenruf/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/morgenruf/morgenruf/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/morgenruf/morgenruf/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/morgenruf/morgenruf/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/morgenruf/morgenruf/releases/tag/v0.1.0
