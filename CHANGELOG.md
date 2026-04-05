# Changelog

All notable changes to Morgenruf are documented here.
Format: [Keep a Changelog](https://keepachangelog.com) | Versioning: [SemVer](https://semver.org)

## [Unreleased]

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
