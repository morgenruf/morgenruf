# Morgenruf 🌅

> **German:** *Morgenruf* — "morning call"

A self-hosted, open-source Slack standup bot. Ask structured daily questions, post formatted summaries to team channels, and keep full ownership of your standup data — no SaaS subscription required.

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
- 📊 **Web dashboard** — Analytics tab, participation stats, CSV export
- 📧 **Welcome email + weekly digest** — via Resend
- 🏠 **App Home tab** — shows workspace status in Slack Home
- 🐳 **Kubernetes-ready** — production Helm chart at `charts.morgenruf.dev`
- ☁️ **Cloudflare Zero Trust** — works behind CF tunnel (no ingress controller needed)
- 🗃️ **PostgreSQL** — full standup history, migrations auto-applied on startup

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
| `help` | Show available commands |

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

---

## Kubernetes Deployment

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
  enabled: true          # set false for Cloudflare Tunnel / custom routing
  className: "nginx"
  hosts:
    - host: api.your-domain.com
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
    ├── configmap.yaml
    └── secret.yaml
```

---

## Deploy

### ☁️ AWS (One-Click CloudFormation)

#### Starter (~$15/mo) — Single EC2 instance
Best for small teams. Runs docker-compose on a single server.

[![Launch Starter Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=morgenruf-starter&templateURL=https://raw.githubusercontent.com/morgenruf/morgenruf/main/deploy/aws/starter.yaml)

EC2 t3.small + PostgreSQL 16 in Docker + Nginx + Elastic IP.

#### Production (~$25/mo) — ECS Fargate Spot + RDS
Zero server management. Auto-healing.

[![Launch Production Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=morgenruf-prod&templateURL=https://raw.githubusercontent.com/morgenruf/morgenruf/main/deploy/aws/production.yaml)

ECS Fargate Spot + RDS PostgreSQL t4g.micro + ALB + ACM + Secrets Manager.

See [`deploy/aws/README.md`](./deploy/aws/README.md) for full setup instructions and parameter reference.

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
