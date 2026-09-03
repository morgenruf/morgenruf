# Changelog

All notable changes to Morgenruf are documented here.
Format: [Keep a Changelog](https://keepachangelog.com) | Versioning: [SemVer](https://semver.org)

## [Unreleased]

### Added
- Helm chart optional Gateway API `HTTPRoute` support (`httpRoute.enabled`, chart v0.5.0)

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
