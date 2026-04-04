# Morgenruf 🌅

## Repository Structure

```
morgenruf/
├── app/        ← Slack bot (Python, Helm chart, Dockerfile)
├── website/    ← Marketing website (Netlify)
├── LICENSE
└── README.md
```

---


> **German:** *Morgenruf* — "morning call"

A self-hosted Slack standup bot that asks your team structured daily standup questions, posts formatted summaries to team channels, and enables per-project reporting.

Built for teams who want full control over their standup data without paying for SaaS tools.

---

## Features

- 📅 **Configurable schedule per team** — different times, timezones, days
- 💬 **DM-based collection** — bot DMs each member, posts structured summary to channel
- 🏗️ **Per-project format** — team prefixes updates with project names (e.g. `Proj-Bridj: ...`)
- 🚧 **Blocker detection** — highlights blockers in each standup
- 🤖 **Manual trigger** — team members can type `standup` in DM anytime
- 🐳 **Kubernetes-ready** — Helm chart included
- ☁️ **Cloudflare Zero Trust compatible** — works behind CF tunnel

---

## Quick Start

### 1. Create a Slack App

1. Go to https://api.slack.com/apps → **Create New App** → From manifest
2. Paste the manifest from [`slack-manifest.yaml`](./slack-manifest.yaml)
3. Install to workspace
4. Copy **Bot Token** (`xoxb-...`) and **Signing Secret**

### 2. Configure teams

```bash
cp teams.yaml.example teams.yaml
# Edit teams.yaml with your team's Slack IDs and schedule
```

### 3. Run locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in .env
python src/main.py
```

### 4. Deploy to Kubernetes

```bash
helm upgrade --install morgenruf ./helm/morgenruf \
  --namespace morgenruf \
  --create-namespace \
  -f helm/morgenruf/values.yaml \
  --set secret.slackBotToken="xoxb-..." \
  --set secret.slackSigningSecret="..."
```

---

## Standup Format

The bot asks 3 questions via DM:

```
✅ What did you complete yesterday?
   > Proj-Bridj: deployed Terraform module, PR #42 merged
   > Proj-Isec: reviewed IAM policies

🎯 What are you working on today?
   > Proj-Bridj: load balancer configuration
   > Proj-Isec: fix SSL cert issue

🚧 Any blockers?
   > Waiting on AWS quota approval
```

The bot then posts a formatted summary to the team channel:

```
📋 Standup from @alice — April 4, 2026

✅ Yesterday:
Proj-Bridj: deployed Terraform module, PR #42 merged
Proj-Isec: reviewed IAM policies

🎯 Today:
Proj-Bridj: load balancer configuration
Proj-Isec: fix SSL cert issue

🚧 Blockers:
Waiting on AWS quota approval
```

---

## Configuration

### `teams.yaml`

```yaml
teams:
  - name: my-team
    channel: "#team-myteam"
    standup_time: "09:00"      # 24h format
    timezone: "Asia/Kolkata"   # pytz timezone
    days: "mon-fri"            # APScheduler day format
    members:
      - slack_id: "U123ABC"
        name: Alice
      - slack_id: "U456DEF"
        name: Bob
```

### Environment variables

| Variable | Required | Description |
|---------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✅ | Bot token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | ✅ | App signing secret |
| `PORT` | | HTTP port (default: `3000`) |

---

## Required Slack Scopes

```
chat:write          Post messages
im:history          Read DM history
im:read             Read DM metadata
im:write            Open DM channels
channels:read       List channels
users:read          Resolve user info
```

Event subscriptions:
```
message.im          DM messages
app_mention         Bot mentions
```

Request URL: `https://standup.yourdomain.com/slack/events`

---

## Kubernetes Deployment

Morgenruf ships with a production-ready Helm chart:

```
helm/morgenruf/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    ├── configmap.yaml
    └── secret.yaml
```

Works with Cloudflare Zero Trust tunnel — point your CF tunnel to the service on port 3000.

---

## Roadmap

- [ ] Per-project standup reports (`morgenruf report --project <name>`)
- [ ] Missed standup reminders
- [ ] Weekly summaries
- [ ] Webhook to external tools (Jira, GitHub)
- [ ] Web dashboard

---

## License

[MIT](./LICENSE)

---

## Contributing

PRs welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.
