# Changelog

All notable changes to Morgenruf are documented here.
Format: [Keep a Changelog](https://keepachangelog.com) | Versioning: [SemVer](https://semver.org)

## [Unreleased]

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
