# Morgenruf 🌅

> **German:** *Morgenruf* — "morning call" · Built over a weekend at a Tim Hortons in Kitchener 🇨🇦☕

[![Release](https://img.shields.io/github/v/release/morgenruf/morgenruf?label=latest&color=brightgreen)](https://github.com/morgenruf/morgenruf/releases)
[![Tests](https://github.com/morgenruf/morgenruf/actions/workflows/test.yml/badge.svg)](https://github.com/morgenruf/morgenruf/actions/workflows/test.yml)
[![Lint](https://github.com/morgenruf/morgenruf/actions/workflows/lint.yml/badge.svg)](https://github.com/morgenruf/morgenruf/actions/workflows/lint.yml)
[![codecov](https://codecov.io/gh/morgenruf/morgenruf/branch/main/graph/badge.svg)](https://codecov.io/gh/morgenruf/morgenruf)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A self-hosted, open-source Slack app for the rituals a distributed team runs on: async standups, random coffee chats, peer recognition, and the cross-signal insights none of them give you alone. Four modules over one deployment and one database, each independently switchable. Keep full ownership of the data, no SaaS subscription required.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Status](https://img.shields.io/badge/status-operational-brightgreen)](https://status.morgenruf.dev)
[![Helm](https://img.shields.io/badge/Helm-3.x-blue)](https://helm.sh)
[![Docker](https://img.shields.io/badge/Docker-DockerHub-blue)](https://hub.docker.com/r/morgenruf/morgenruf)

---

## Repository Structure

```
morgenruf/
├── app/
│   ├── src/            ← Python bot (Flask + slack-bolt)
│   ├── migrations/     ← SQL migration files (auto-applied on start)
│   ├── helm/morgenruf/ ← Production Helm chart
│   └── Dockerfile
├── brand/              ← Logo & brand assets
├── slack-manifest.yaml ← Slack app manifest
├── CHANGELOG.md
└── README.md
```

---

## Features

- 📅 **Configurable schedule** — per-team times, timezones, and days
- 💬 **DM-based collection** — bot DMs each member individually
- ❓ **Custom questions** — fully editable from the dashboard (not hardcoded)
- ⏭️ **Skip today** — DM `skip` to opt out for the day
- ⏰ **Pre-standup reminder** — configurable minutes before standup time
- 🌍 **Per-user timezone** — DM `timezone America/New_York` to set personal timezone
- 🚧 **Blocker detection** — highlights blockers in summaries
- 🤖 **Manual trigger** — type `standup` in DM anytime
- 🎭 **Mood tracking** — 4th question captures team sentiment (😊/😐/😔)
- 🔗 **Auto-linking** — Jira/GitHub issue references become clickable links
- 🪝 **Webhooks** — HMAC-signed HTTP webhooks on `standup.completed`
- ✏️ **Edit window** — members can edit responses within a configurable time window
- 🔔 **Nudge** — whoever has not filed by report time gets a private reminder
- 📊 **Web dashboard** — Analytics tab, participation stats, CSV export
- 🩺 **Standup health** — fourteen days of completion on the card, with a badge when it slips
- 👥 **Per-feature admins** — hand one person the standups and another the coffee chats, without giving either the workspace
- 📧 **Welcome email + weekly digest** — via Resend
- 🏠 **App Home tab** — shows workspace status in Slack Home
- 🐳 **Kubernetes-ready** — production Helm chart at `charts.morgenruf.dev`
- ☁️ **Cloudflare Zero Trust** — works behind CF tunnel (no ingress controller needed)
- 🗃️ **PostgreSQL** — full standup history, migrations auto-applied on startup

---

## Modules

Morgenruf ships as four modules over one deployment and one database. Each one
is independent: it owns its own migrations, Slack handlers, dashboard routes and
scheduled jobs, and can be switched off without touching the others.

| Module | What it does | On by default |
|---|---|---|
| **Standups** | Async daily standups, summaries, mood, blockers, webhooks | Yes |
| **Coffee chats** | Random 1:1 pairings from a channel on a cadence, history-aware so the same two people are not matched twice in a row | No — needs extra scopes |
| **Kudos** | Peer recognition with a daily allowance, a custom token, and leaderboards for receivers *and* givers | Yes |
| **Insights** | Questions that need two signals at once: blockers nobody has cleared in days, people who answer every standup and are thanked by nobody | Yes |

A module is only live when all four gates pass, checked in order:

1. **Deploy allowlist** — `MORGENRUF_MODULES=standup,kudos` ships a build with the
   others present but dark. Unset means no restriction.
2. **Granted scopes** — Coffee chats needs `mpim:write`, `mpim:history` and
   `users.profile:read`. A workspace that installed before those scopes existed
   stays dark until it re-authorises, rather than erroring at runtime.
3. **Workspace toggle** — per-workspace, from the dashboard.
4. **Module default** — what a workspace that has never chosen gets.

### Coffee chats

Pick a channel and a cadence. Everyone in it is paired and introduced in a group
DM; when the count is odd, one group of three forms so nobody sits out. Matching
is history-aware, so the same two people are not put together twice running.

**The introduction carries the meeting, not just the names.** A programme can
hold a room everyone uses and a chat length, and where two people's working days
overlap it proposes hours that suit both, each one a click away from their
calendar. The wording is careful on purpose:

> These fit everyone's working hours. Nobody has checked your calendars, so pick
> whichever is actually free.

Without calendar access we can say an hour suits their timezones, never that
they are free. Implying otherwise would be worse than offering nothing.

**Agreeing a time.** The pair is offered hours that suit both of them and votes
with a button. When both pick the same one, that is the meeting. With Zoom
connected, the meeting is created at that hour and the link goes back into the
conversation; without it, the programme's own room is used, or none at all.
Linking Zoom is per person, from the message itself, and revoking it affects
nobody else.

Group size runs from 2 to 8. A remainder of two or more forms its own group
rather than being folded into a larger one, so ten people in fours are 4, 4 and
2, not 5 and 5. Anyone can ask for a different match, once per round.

Three days later the bot nudges pairs that have not met, and closes the round on
day six by asking whether they did. That answer is reported four ways rather
than two: **met**, **did not meet**, **no reply**, and **not delivered**. The
last is a delivery failure on our side, not people failing to show up, and
folding it into "did not meet" would blame them for our bug.

**Run now** starts a round without waiting for the cadence, so a programme can be
tried the day it is set up. **Snooze** takes someone out for a fortnight from the
Slack App Home, which is where they will think to look.

**Match on working hours** is a per-programme switch, off by default and worth
leaving off unless you know it applies. A nine-to-five in Toronto and one in
Kolkata share no hours at all, so turning it on for a team spread that widely
stops matching them entirely.

### Kudos

`kudos @teammate nice work on the deploy` in a DM to the bot. Each person gets a
daily allowance that resets at midnight *in their own timezone*, and unused ones
do not carry over — that is what makes people spend them.

**Using the Morgenruf icon as your kudos token:** download it from **Kudos → The
token your team gives**, add it in Slack under **Customize workspace → Add custom
emoji** with the name `morgenruf`, and the bot picks it up within a day on its
own. It falls back if the emoji is ever removed, so a workspace never ends up
posting `:morgenruf:` as literal text.

Setting the token by hand switches that off and keeps whatever you choose.
Changing the daily allowance does not: the settings form submits every field, and
treating any save as a token choice used to opt workspaces out of the emoji they
had just imported.

---

## Who can change what

Two roles, plus a grant per feature.

| | Workspace admin | Feature admin | Member |
|---|---|---|---|
| Standups: create, edit, delete, automation rules | yes | with the standups grant | no |
| Coffee chats: programmes, members, run a round now | yes | with the coffee chats grant | no |
| Kudos: allowance and token | yes | with the kudos grant | no |
| Roles, invitations, API keys, webhooks, the public feed, feature switches | yes | no | no |
| Reading any page | yes | yes | yes |

A workspace admin hands a feature over from **Members**: each card carries a chip
per feature, pressed to give it and pressed again to take it back. The team lead
runs the standups, someone in HR runs coffee chats and kudos, and neither of them
can mint an API key or publish the workspace's standups at a public URL.

The person who installed the app always counts as an admin, whatever the members
table says, so a workspace cannot lock itself out. Demoting the last admin is
refused for the same reason.

---

## Quick Start

### 1. Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From manifest
2. Paste the manifest from [`slack-manifest.yaml`](./slack-manifest.yaml)
3. Under **OAuth & Permissions**, add your redirect URL: `https://<your-domain>/oauth/callback`
4. Copy **Client ID**, **Client Secret**, and **Signing Secret**

### 2. Run locally

```bash
cd app
cp .env.example .env
# Fill in SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_SIGNING_SECRET, DATABASE_URL
pip install -r src/requirements.txt
python src/main.py
```

### 3. Deploy to Kubernetes

See [**Kubernetes Deployment**](#kubernetes-deployment) below.

---

## Docker Image

Available on DockerHub: [`morgenruf/morgenruf`](https://hub.docker.com/r/morgenruf/morgenruf)

```bash
docker pull morgenruf/morgenruf:latest
```

Also mirrored at `ghcr.io/morgenruf/morgenruf:latest`

### GitHub Actions / CI

The image is automatically built and pushed on every push to `main` and on version tags (`v*`) via `.github/workflows/docker-publish.yml`.

If you fork this repo, add the following secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | `morgenruf` |
| `DOCKERHUB_TOKEN` | Your DockerHub access token |

## Docker / Mac Quickstart

The fastest way to run Morgenruf locally or on a Mac server.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac/Linux/Windows)
- A Slack app — [create one](https://api.slack.com/apps) using the manifest at `slack-manifest.yaml`

### 1. Clone and configure

```bash
git clone https://github.com/morgenruf/morgenruf
cd morgenruf/app
cp .env.example .env
# Edit .env with your Slack credentials
```

### 2. Start

```bash
docker compose up -d
```

That's it. The bot is now running at `http://localhost:3000`.

### 3. Expose to the internet (required for Slack webhooks)

Slack needs to reach your bot. Options:

**Cloudflare Tunnel (recommended — free, no port forwarding):**
```bash
brew install cloudflare/cloudflare/cloudflared
cloudflared tunnel --url http://localhost:3000
# Copy the https://xxxx.trycloudflare.com URL
# Set APP_URL=https://xxxx.trycloudflare.com in .env
# docker compose restart app
```

**ngrok:**
```bash
ngrok http 3000
# Copy the https URL and set APP_URL in .env
```

### 4. Configure your Slack app

Set these URLs in your Slack app settings:
- **Event Subscriptions Request URL:** `https://your-tunnel-url/slack/events`
- **OAuth Redirect URL:** `https://your-tunnel-url/oauth/callback`
- **Interactivity Request URL:** `https://your-tunnel-url/slack/interactions`

Then click **"Add to Slack"** from `https://your-tunnel-url/install`.

### Mac as a permanent server

To run on a Mac Mini or Mac server permanently:

```bash
# Start on boot
brew services start docker  # or use Docker Desktop login items

# Keep containers running
docker compose up -d --restart-policy always
```

---

## Google Chat (Beta)

Morgenruf supports Google Chat via the Chat REST API and a service account.

> **Note:** Google Chat bot integration requires **Google Workspace** (not free Gmail accounts).

### Setup

1. **Create a GCP project** at [console.cloud.google.com](https://console.cloud.google.com)
2. **Enable the Chat API** — _APIs & Services → Library → Google Chat API → Enable_
3. **Create a service account** — _IAM & Admin → Service Accounts → Create_
4. **Download the JSON key** for the service account
5. **Set the env var** — paste the entire JSON as a single line:
   ```bash
   GOOGLE_CREDENTIALS='{"type":"service_account","project_id":"...","private_key":"...","client_email":"...",...}'
   ```
6. **Configure the bot in Google Chat Admin** — _admin.google.com → Apps → Google Chat → Manage bots_
   - Set the **Webhook URL** to: `https://your-domain.com/google/events`
   - Enable _Direct messages_ and _Space messages_
7. **Restart Morgenruf** — the Google Chat blueprint is registered automatically when `GOOGLE_CREDENTIALS` is set.

### Commands (in Google Chat DM or Space)

| Command | Description |
|---------|-------------|
| `/standup` | Start your daily standup |
| `/skip` | Skip today's standup |
| `/help` | Show available commands |

---

## Standup Format

The bot DMs each member 4 questions:

```
✅ What did you complete yesterday?
🎯 What are you working on today?
🚧 Any blockers?
🎭 How are you feeling today? (😊 Great / 😐 Okay / 😔 Struggling)
```

Then posts a formatted summary to the configured channel:

```
📋 Standup — Alice  |  April 5, 2026

✅ Yesterday
  Deployed Terraform module, PR #42 merged

🎯 Today
  Load balancer configuration

🚧 Blockers
  Waiting on AWS quota approval

🎭 Mood: 😊
```

---

## DM Commands

| Command | Description |
|---------|-------------|
| `standup` | Start your standup now |
| `skip` | Skip today's standup |
| `timezone <tz>` | Set your personal timezone (e.g. `timezone Europe/London`) |
| `kudos @teammate <reason>` | Give someone recognition (also `/kudos`) |
| `help` | Show available commands |

Coffee chat replies are buttons rather than typed commands — **We met**, **Not
this time**, **Skip this round** and **Pause** appear on the messages the bot
sends, so nothing there can collide with `skip`.

---

## MCP Server

Morgenruf exposes its data to AI assistants over MCP, so you can ask questions
in plain language instead of reading dashboards. Generate a key in the
dashboard under **MCP**, then point your client at `https://api.morgenruf.dev/mcp`
with an `Authorization: Bearer <key>` header.

**`tools/list` is per-workspace.** Only modules that pass all four activation
gates advertise their tools, so an assistant is never offered a tool for a
feature the workspace has switched off.

| Area | Tools |
|---|---|
| Standups | `get_standups`, `get_today_standups`, `get_blockers`, `get_participation`, `get_members`, `search_standups`, `get_workspace_summary`, `get_mood_summary` |
| Kudos | `get_kudos_leaderboard`, `get_recent_kudos`, `get_kudos_settings` |
| Coffee chats | `list_coffee_chat_programs`, `get_coffee_chat_rounds`, `get_coffee_chat_attendance`, `get_coffee_chat_pairs` |
| Insights | `get_stuck_blockers`, `get_unrecognised_contributors` |

Questions these make answerable: *"who has been blocked on the same thing for
days?"*, *"who answers standup every day and has never been thanked?"*, *"which
coffee chat pairings never actually happened?"*

Full reference: [docs.morgenruf.dev/mcp.html](https://docs.morgenruf.dev/mcp.html)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_CLIENT_ID` | ✅ | Slack app client ID |
| `SLACK_CLIENT_SECRET` | ✅ | Slack app client secret |
| `SLACK_SIGNING_SECRET` | ✅ | Request signing secret |
| `DATABASE_URL` | ✅ | PostgreSQL connection URL |
| `APP_URL` | ✅ | Public base URL (e.g. `https://api.morgenruf.dev`) |
| `FLASK_SECRET_KEY` | ✅ | Random secret for session cookies |
| `PORT` | | HTTP port (default: `3000`) |
| `RESEND_API_KEY` | | For welcome emails (optional) |
| `ZOOM_CLIENT_ID` | | Zoom account linking (optional, see below) |
| `ZOOM_CLIENT_SECRET` | | Zoom account linking (optional, see below) |

---

## Zoom meetings (optional)

Each person connects their own Zoom account from the Morgenruf tab in Slack.
After that, a coffee chat gets a real meeting **scheduled for the time the pair
agree**, hosted on the account of whoever in the pairing has connected.

Leave the two variables unset and the feature is absent rather than broken: no
button appears and nothing fails.

1. Create a **user-managed** OAuth app at
   <https://marketplace.zoom.us/develop/create>.
2. Set its redirect URL to `<APP_URL>/connect/zoom/callback`.
3. Give it the scopes `meeting:write:meeting` and `user:read:user`.
4. Set `ZOOM_CLIENT_ID` and `ZOOM_CLIENT_SECRET`, or `zoom.clientId` and
   `zoom.clientSecret` in the Helm chart.

Both must be set. With only one, the feature stays off rather than half on.

**Distribution.** An unpublished Zoom app can only be installed by users inside
your own Zoom account, which is enough to try it. Letting other workspaces
connect requires publishing the app on the Zoom Marketplace, which goes through
their review.

Anyone can disconnect their own account from the same Morgenruf tab. Zoom
refresh tokens also expire after 90 days unused, and the tab says "reconnect"
rather than showing an unlinked state, so a link that aged out is
distinguishable from one that was never made.

The dashboard shows Zoom's own mark next to the setting, from
[Simple Icons](https://simpleicons.org) (CC0), as it does for Slack, Google Meet
and Microsoft Teams. It marks the integration, never Morgenruf itself: Zoom's
Partner Brand Guide governs use of the mark, and their app review keeps another
company's logo off your app icon.

---

## Kubernetes Deployment

> **On the bundled database.** `postgresql.enabled=true` runs a single
> StatefulSet using the official `postgres` image, which is what this project's
> own production deployment uses. It replaced a Bitnami subchart whose images
> were withdrawn from Docker Hub, so any chart before **0.9.0** fails on that
> path with `ErrImagePull`. It is there for trials; anything with real data
> behind it should use `externalDatabase.url`.
>
> The password is required when the bundled database is enabled. Generate one
> with `openssl rand -hex 16` and keep it in your values file: changing it later
> will not change the password already initialised inside the volume.

Morgenruf ships a production-ready Helm chart at `app/helm/morgenruf/`.

### Database (recommended: external PostgreSQL)

> **We recommend using an external PostgreSQL instance** rather than the bundled sub-chart.
> The bundled sub-chart is convenient for testing but adds operational complexity in production.
> Bitnami images were also removed from Docker Hub, which can cause pull failures.

**Good options:**
- [CloudNativePG](https://cloudnative-pg.io/) operator (k8s-native)
- [Supabase](https://supabase.com) / [Neon](https://neon.tech) (managed, free tiers)
- AWS RDS / Google Cloud SQL / Azure Database
- Plain `postgres:16` StatefulSet in your cluster

Once you have a database, create the database and user:

```sql
CREATE DATABASE morgenruf;
CREATE USER morgenruf WITH PASSWORD 'strongpassword';
GRANT ALL PRIVILEGES ON DATABASE morgenruf TO morgenruf;
```

### Install

```bash
helm repo add morgenruf https://charts.morgenruf.dev
helm repo update

helm upgrade --install morgenruf morgenruf/morgenruf \
  --namespace morgenruf \
  --create-namespace \
  --set slack.clientId="YOUR_CLIENT_ID" \
  --set slack.clientSecret="YOUR_CLIENT_SECRET" \
  --set slack.signingSecret="YOUR_SIGNING_SECRET" \
  --set externalDatabase.url="postgresql://morgenruf:pass@host:5432/morgenruf" \
  --set flaskSecretKey="$(openssl rand -hex 32)" \
  --set app.url="https://api.your-domain.com"
```

> **Migrations** run automatically as an init container on every pod start — idempotent and safe.

### Cloudflare Zero Trust (no ingress controller)

If you use Cloudflare Tunnel instead of an ingress controller:

```bash
# Disable ingress in Helm
--set ingress.enabled=false

# Then add a Public Hostname in Cloudflare Zero Trust dashboard:
# Hostname: api.your-domain.com
# Service:  http://morgenruf.morgenruf.svc.cluster.local:3000
```

### Gateway API (HTTPRoute)

If your cluster uses [Gateway API](https://gateway-api.sigs.k8s.io/) instead of (or in addition to) Ingress, enable the chart's HTTPRoute and point it at your Gateway:

```bash
helm upgrade --install morgenruf morgenruf/morgenruf \
  --namespace morgenruf \
  --create-namespace \
  --set ingress.enabled=false \
  --set httpRoute.enabled=true \
  --set httpRoute.hostName="api.your-domain.com" \
  --set httpRoute.gateway.name="morgenruf-gateway" \
  --set httpRoute.gateway.namespace="morgenruf" \
  # ... plus required slack / database / app.url values
```

Requires Gateway API CRDs and an existing Gateway that matches `httpRoute.gateway`. Disable Ingress when HTTPRoute owns the hostname so you don't double-route the same host.

### values.yaml reference

```yaml
# Required ─────────────────────────────────────────────
slack:
  clientId: ""           # Slack app → Basic Information → Client ID
  clientSecret: ""       # Slack app → Basic Information → Client Secret (32 chars)
  signingSecret: ""      # Slack app → Basic Information → Signing Secret

externalDatabase:
  url: ""                # postgresql://user:pass@host:5432/db

flaskSecretKey: ""       # openssl rand -hex 32

app:
  url: "https://api.your-domain.com"   # Public HTTPS URL for OAuth redirects

# Optional ─────────────────────────────────────────────
resend:
  apiKey: ""             # Resend API key for welcome emails (free tier ok)

ingress:
  enabled: true          # set false for Cloudflare Tunnel / Gateway API / custom routing
  className: "nginx"
  hosts:
    - host: api.your-domain.com

httpRoute:
  enabled: false         # set true for Gateway API HTTPRoute
  hostName: "api.your-domain.com"
  gateway:
    name: morgenruf-gateway
    namespace: morgenruf
```

> ⚠️ **Common mistake:** `slack.clientSecret` and `slack.signingSecret` are **different values**.  
> Both are found on your Slack app's **Basic Information** page.  
> — Client Secret: 32 hex chars (e.g. `346a428c78b0d8c84b70e74d12a58ab5`)  
> — Signing Secret: 32 hex chars, listed separately under "App Credentials"

---

## Helm Chart Structure

```
app/helm/morgenruf/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml   ← init container runs migrations
    ├── service.yaml
    ├── ingress.yaml
    ├── httproute.yaml    ← Gateway API HTTPRoute (optional)
    ├── redis.yaml
    ├── configmap.yaml
    └── secret.yaml
```

---

## Deploy

---

## Roadmap

- [x] Multi-workspace Slack OAuth
- [x] Web dashboard (`/dashboard`)
- [x] Webhooks with HMAC signing
- [x] Jira/GitHub auto-linking
- [x] Edit window for responses
- [x] Email notifications (Resend)
- [x] Custom questions
- [x] Skip today
- [x] Pre-standup reminders
- [x] Per-user timezone
- [x] Mood tracking
- [x] Analytics dashboard + CSV export
- [x] Weekly digest email
- [ ] Multiple standup schedules per workspace
- [ ] Jira/Linear/GitHub integration
- [ ] Microsoft Teams support *(coming soon)*
- [ ] Public REST API

---

## License

[MIT](./LICENSE)

---

## Contributing

PRs welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---


