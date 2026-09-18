# Morgenruf Roadmap

This roadmap outlines what's been shipped, what's in progress, and what's planned. It's a living document — priorities may shift based on community feedback.

Have an idea? [Open a discussion](https://github.com/morgenruf/morgenruf/discussions/new?category=ideas) or [vote on existing ones](https://github.com/morgenruf/morgenruf/discussions).

---

## ✅ Shipped

### v1.0.0 — April 2026
- Slack OAuth install flow with persistent token store
- Daily standup DM flow with configurable questions
- Standup summary posted to channel
- Web dashboard — manage standups, schedules, team settings
- Role-based access control (admin / member)
- Multiple standup schedules per workspace
- Per-user timezone support
- Skip today command
- Reminder notifications
- Mood tracking
- Analytics dashboard with participation charts
- CSV export
- Weekly digest email
- Webhook integrations
- AI standup summary (OpenAI GPT-4o-mini / Anthropic Claude Haiku)
- Workflow automation rules engine
- Kudos / peer recognition system
- 25 pre-built question templates
- Jira / GitHub / Linear auto-linking
- MCP server at `/mcp` (Claude, Cursor, GitHub Copilot)
- Google Chat adapter (Beta)
- Kubernetes-ready Helm chart
- Public status page ([status.morgenruf.dev](https://status.morgenruf.dev))
- Full documentation ([docs.morgenruf.dev](https://docs.morgenruf.dev))
- 80-test Playwright E2E suite

### v1.1 to v1.6 — April to September 2026

Modal standup forms, schedule-scoped threads, HTTPRoute support, a rebuilt
Analytics page, member sync, a security fix, and a standup that tells you when
it will never fire. Release by release in [CHANGELOG.md](CHANGELOG.md).

### v1.7 — September 2026: four modules

- Module contract: each feature owns its migrations, Slack handlers, dashboard
  routes and scheduled jobs, and can be switched off per workspace
- **Coffee chats**: pairings from a channel on a cadence, history-aware so the
  same two people are not matched twice running; odd numbers form a group of
  three; groups of two to eight
- Introductions carry an opener, a room, and hours that suit both people
- Nudge on day three, close on day six, reported four ways (met, did not meet,
  no reply, not delivered)
- **Kudos** leaderboards for receivers and givers, allowance resetting at
  midnight in each person's own timezone, branded token
- **Insights**: blockers nobody has cleared, people thanked by nobody
- Coffee chats on the Slack App Home, with pause and snooze
- Per-standup digest email, replacing one workspace-wide address

### v1.8 — September 2026: delegation, and a lot of honesty

- **Per-feature admins**: one person runs standups, another runs coffee chats
  and kudos, neither can mint API keys or publish the workspace's standups
- Coffee chats settle on a time: the pair votes, and Zoom books the hour
- Standup nudge for whoever has not filed by report time
- Standup health on each card: fourteen days of completion, and a badge when
  it slips
- Feature switches in Settings
- Fixed: fourteen mutating routes a plain member could reach, a workspace that
  could lock itself out, every workspace-level setting being unwritable since
  inception, and about twenty controls that saved and did nothing

---

## 🚧 In Progress

- **MS Teams adapter** — Bot Framework SDK, Adaptive Cards, Azure AD OAuth
- **Slack App Directory submission** — listing, screenshots, review

---

## 📋 Planned

### Next modules

- [ ] **Celebrations** — birthdays and work anniversaries announced in a
      channel on the day, with the roster held in Morgenruf
- [ ] **Calendar** — hold the hour a coffee chat pair agreed on their
      calendars. Google Calendar first, which is a sensitive rather than a
      restricted scope, so it does not need a paid security assessment
- [ ] **Meet and Teams rooms** created for a pairing the way Zoom already is
- [ ] **Onboarding journeys** — a sequence over someone's first fortnight

### Integrations
- [ ] PagerDuty / OpsGenie on-call awareness (skip standup when on-call)
- [ ] GitHub PR / issue auto-embed in summaries
- [ ] Linear cycle sync
- [ ] Notion standup export

### Collaboration
- [ ] Team standup templates (Engineering, Design, Support presets)
- [ ] Threaded replies to standup summaries in Slack
- [ ] Cross-team blocker visibility dashboard
- [ ] Public standup feed embeds (iframe)

### Self-hosting UX
- [ ] One-click Railway / Render deploy button
- [ ] Docker Compose setup wizard
- [ ] First-run onboarding wizard (no YAML required)
- [ ] Admin UI for environment variable management

### Multi-platform
- [ ] Discord adapter
- [ ] Microsoft Teams GA (out of beta)
- [ ] Google Chat GA (out of beta)
- [ ] Unified cross-platform dashboard

---

## 💡 Ideas Under Consideration

- Async video standup integration (Loom, Claap)
- Mobile push notifications via Slack
- SAML / SSO for enterprise self-hosters
- Standup streaks and gamification
- LLM-powered blocker detection and escalation

---

*Last updated: September 2026, at 1.8.4.*
