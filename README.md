# Morgenruf 🌅

> **German:** *Morgenruf* — "morning call"

A self-hosted, open-source Slack standup bot. Ask structured daily questions, post formatted summaries to team channels, and keep full ownership of your standup data — no SaaS subscription required.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Helm](https://img.shields.io/badge/Helm-3.x-blue)](https://helm.sh)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue)](https://ghcr.io/morgenruf/morgenruf)

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
- 🏗️ **Per-project format** — prefix updates with project names (e.g. `Proj-X: ...`)
- 🚧 **Blocker detection** — highlights blockers in summaries
- 🤖 **Manual trigger** — type `standup` in DM anytime
- 🔗 **Auto-linking** — Jira/GitHub issue references become clickable links
- 🪝 **Webhooks** — fire HTTP webhooks on standup submission
- ✏️ **Edit window** — members can edit responses within a configurable time window
- 📊 **Web dashboard** — manage teams, view history at `/dashboard`
- 🐳 **Kubernetes-ready** — production Helm chart included
- ☁️ **Cloudflare Zero Trust** — works behind CF tunnel (no ingress controller needed)

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

## Standup Format

The bot DMs each member 3 questions:

```
✅ What did you complete yesterday?
🎯 What are you working on today?
🚧 Any blockers?
```

Then posts a formatted summary to the configured channel:

```
📋 Standup — Alice  |  April 5, 2026

✅ Yesterday
  Proj-Bridj: deployed Terraform module, PR #42 merged

🎯 Today
  Proj-Bridj: load balancer configuration

🚧 Blockers
  Waiting on AWS quota approval
```

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

## Roadmap

- [x] Multi-workspace Slack OAuth
- [x] Web dashboard (`/dashboard`)
- [x] Webhooks with HMAC signing
- [x] Jira/GitHub auto-linking
- [x] Edit window for responses
- [x] Email notifications (Resend)
- [ ] Microsoft Teams support *(coming soon)*
- [ ] Google Chat support *(coming soon)*
- [ ] MCP / AI Integration *(coming soon)*
- [ ] Per-project standup reports
- [ ] Public REST API (v0.3)
- [ ] Slack App Directory listing

---

## License

[MIT](./LICENSE)

---

## Contributing

PRs welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.
