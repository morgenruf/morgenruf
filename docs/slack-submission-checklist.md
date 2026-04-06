# Slack App Directory Submission Checklist

> **App:** Morgenruf — Daily standups for Slack  
> **Category:** Productivity  
> Reference this document before submitting to the [Slack App Directory](https://api.slack.com/start/distributing).

---

## 1. App Listing Content

### Short Description (≤150 chars)
```
Free, open-source Slack standup bot. Schedule daily standups, collect answers privately, post clean summaries to your team channel.
```
*(130 chars)*

### Long Description
```
Morgenruf runs your team's daily standups directly in Slack — no expensive SaaS subscription required.

Each day at your configured time, Morgenruf DMs each team member with your custom questions, collects answers privately, and posts a clean formatted summary to your team channel — including blocker highlighting and mood tracking.

Key highlights:
• 100% free and open-source (MIT) — self-host or use the hosted version at morgenruf.dev
• No per-user pricing, no credit card required
• Fully configurable: schedule, timezone, custom questions, reminder timing
• Blocker detection automatically highlights impediments in summaries
• Mood tracking captures team sentiment on every standup
• Per-user timezone support so globally distributed teams stay in sync
• Edit window lets members correct answers after submission
• Web dashboard with analytics, participation stats, and CSV export
• Webhooks for integrating standup data with your own tools
• App Home tab shows workspace standup status at a glance
• Kubernetes-ready with a production Helm chart

Morgenruf is a drop-in replacement for Geekbot, Standup & Prosper, and similar paid tools — with full data ownership.
```

### App Category Recommendation
- **Primary:** Productivity
- **Secondary:** Project Management

### Key Features (bullet points for listing)
- Automated daily standup scheduling with configurable time, timezone, and days
- Private DM-based question collection — answers never exposed in channels until summary
- Custom questions — fully editable from the web dashboard
- Blocker detection and highlighting in team summaries
- Mood tracking (😊 / 😐 / 😔) on every standup
- Per-user timezone support for distributed teams
- Configurable pre-standup reminders
- Edit window for post-submission corrections
- Skip command (`skip`) for individual opt-out
- Web dashboard with participation analytics and CSV export
- HMAC-signed webhooks on `standup.completed`
- App Home tab with workspace standup status
- 100% open-source (MIT) — self-host or use morgenruf.dev

---

## 2. Required Assets Checklist

### App Icon
- [ ] **512×512 px** — required for App Directory listing (PNG, no transparency)
- [ ] **192×192 px** — used in search results and install prompts
- [ ] **88×88 px** — used in Slack workspace sidebar (auto-generated from 512, but verify)
- [ ] Icon should work on both light and dark backgrounds
- [ ] Source files are in `/brand/` directory

### Screenshots
Slack requires at least **3 screenshots** (1280×800 px or 2560×1600 px @2x, PNG/JPG):

- [ ] **Screenshot 1 — Bot DM flow**: Bot sending the first standup question to a user in DM
- [ ] **Screenshot 2 — Full DM conversation**: Complete Q&A exchange between user and bot
- [ ] **Screenshot 3 — Channel summary**: The formatted standup summary posted to a team channel, with blocker highlighting
- [ ] **Screenshot 4 — App Home tab**: The Slack App Home tab showing workspace standup status
- [ ] **Screenshot 5 — Web dashboard**: Analytics/participation view from the web dashboard (optional but recommended)

### Banner / Hero Image
- [ ] **1200×600 px** (PNG/JPG) — used on the App Directory detail page
- [ ] Should include app name, tagline, and a visual of the product in action

---

## 3. Technical Review Checklist

### OAuth Scopes Justification

| Scope | Justification |
|---|---|
| `chat:write` | Post standup summaries to team channels and send DMs to users |
| `chat:write.public` | Post summaries to public channels the bot hasn't explicitly joined |
| `im:history` | Read DM messages to receive standup answers and commands (`skip`, `timezone`, `standup`) |
| `im:read` | List and access DM channels with users |
| `im:write` | Open DM channels to send standup questions |
| `channels:read` | List channels to let admins configure which channel receives summaries |
| `channels:join` | Join the configured summary channel to post there |
| `channels:history` | Read channel history for App Home context and mention handling |
| `groups:read` | List private channels so teams can configure a private channel as the summary destination |
| `reactions:write` | Add emoji reactions to standup summaries (e.g., acknowledge blockers) |
| `users:read` | Look up user display names and status for standup participation tracking |
| `users:read.email` | Associate Slack users with workspace accounts for the web dashboard |
| `team:read` | Retrieve workspace name and domain for multi-workspace support and dashboard display |
| `app_mentions:read` | Receive `@Morgenruf` mentions so users can trigger commands from channels |

### Event Subscriptions Justification

| Event | Justification |
|---|---|
| `app_home_opened` | Render the App Home tab with the workspace's standup status when a user opens it |
| `app_mention` | Handle `@Morgenruf` commands triggered from channels |
| `message.im` | Receive standup answers and text commands (`skip`, `timezone`, `standup`) sent in DMs |
| `member_joined_channel` | Detect when the bot joins a channel so it can confirm configuration |

### URLs & Policies
- [x] **Privacy policy URL**: https://morgenruf.dev/privacy
- [x] **Support URL**: https://morgenruf.dev/support
- [ ] **Terms of service URL**: https://morgenruf.dev/terms — *verify page exists and is live*
- [ ] **Data retention policy**: Document how long standup responses are stored; add to privacy policy
  - Standup data is stored in the operator's own PostgreSQL database (self-hosted)
  - For the hosted version (morgenruf.dev), define and publish retention period

### Required Capabilities
- [x] **Bot user** (`always_online: true`) — needed for scheduled standup delivery
- [x] **App Home tab** — enabled (`home_tab_enabled: true`)
- [x] **Interactivity** — enabled for button/action responses in DMs
- [x] **Token rotation** — enabled (`token_rotation_enabled: true`)
- [ ] **org_deploy_enabled** — currently `false`; set to `true` only if submitting for Enterprise Grid

### Additional Technical Checks
- [ ] Verify `token_rotation_enabled: true` is handled in code (token refresh logic implemented)
- [ ] Confirm `SLACK_SIGNING_SECRET` verification is applied to all incoming requests
- [ ] Confirm HTTPS is enforced on all endpoints (`/slack/events`, `/slack/interactions`, `/oauth/callback`)
- [ ] Confirm rate limiting and error handling for Slack API calls
- [ ] Confirm graceful handling of `app_uninstalled` / `tokens_revoked` events (data cleanup)

---

## 4. Pre-Submission Verification Steps

### Fresh Install Test
- [ ] Create a new Slack test workspace (free plan is fine)
- [ ] Install Morgenruf from scratch via `https://<your-domain>/install`
- [ ] Complete the OAuth flow — verify redirect lands correctly and token is stored
- [ ] Confirm the App Home tab loads after install

### Slash Commands / DM Commands
- [ ] DM `standup` — bot sends all configured questions immediately
- [ ] Answer all questions and confirm the summary posts to the configured channel
- [ ] DM `skip` — bot acknowledges and skips today's standup for that user
- [ ] DM `timezone America/New_York` — bot confirms timezone was updated
- [ ] DM `help` — bot responds with available commands
- [ ] Mention `@Morgenruf` in a channel — verify bot responds appropriately

### Scheduled Standup
- [ ] Configure a standup time 5 minutes in the future
- [ ] Confirm DMs go out on schedule
- [ ] Confirm summary posts to the correct channel after all responses (or after timeout)
- [ ] Confirm blocker highlighting appears when a response contains blocker keywords

### Edit Window
- [ ] Submit a standup answer, then re-send an edited answer within the edit window
- [ ] Confirm the summary reflects the updated answer

### OAuth Flow
- [ ] Uninstall the app from the test workspace
- [ ] Confirm `tokens_revoked` or `app_uninstalled` event is handled (no orphaned data issues)
- [ ] Reinstall — confirm a clean fresh setup with no residual data issues

### Uninstall / Reinstall
- [ ] Uninstall and reinstall — verify the app recovers cleanly
- [ ] Check that no duplicate DMs or summaries are sent

### Multi-Workspace (if applicable)
- [ ] Install to a second test workspace
- [ ] Verify workspace isolation — workspace A data does not appear in workspace B

---

## 5. Submission Checklist Summary

| Item | Status |
|---|---|
| Short description (≤150 chars) written | ⬜ |
| Long description written | ⬜ |
| App icon 512×512 ready | ⬜ |
| App icon 192×192 ready | ⬜ |
| 3+ screenshots ready (1280×800) | ⬜ |
| Banner image ready (1200×600) | ⬜ |
| Privacy policy URL live | ✅ |
| Support URL live | ✅ |
| Terms of service URL live | ⬜ |
| Data retention policy documented | ⬜ |
| All OAuth scopes justified | ✅ |
| All events justified | ✅ |
| Token rotation handled in code | ⬜ |
| Fresh install tested | ⬜ |
| All DM commands tested | ⬜ |
| OAuth + uninstall/reinstall tested | ⬜ |
| Scheduled standup tested end-to-end | ⬜ |
