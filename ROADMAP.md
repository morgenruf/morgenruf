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

---

## 🚧 In Progress

- **MS Teams adapter** — Bot Framework SDK, Adaptive Cards, Azure AD OAuth
- **Slack App Directory submission** — listing, screenshots, review

---

## 📋 Planned

### v1.1 — Integrations
- [ ] PagerDuty / OpsGenie on-call awareness (skip standup when on-call)
- [ ] GitHub PR / issue auto-embed in summaries
- [ ] Linear cycle sync
- [ ] Notion standup export

### v1.2 — Collaboration
- [ ] Team standup templates (Engineering, Design, Support presets)
- [ ] Threaded replies to standup summaries in Slack
- [ ] Cross-team blocker visibility dashboard
- [ ] Public standup feed embeds (iframe)

### v1.3 — Self-hosting UX
- [ ] One-click Railway / Render deploy button
- [ ] Docker Compose setup wizard
- [ ] First-run onboarding wizard (no YAML required)
- [ ] Admin UI for environment variable management

### v2.0 — Multi-platform
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

*Last updated: April 2026*
