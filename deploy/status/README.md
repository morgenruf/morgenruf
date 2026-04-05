# Morgenruf Status Page

Public uptime monitoring at [status.morgenruf.dev](https://status.morgenruf.dev)

## Setup (5 minutes, free)

1. Sign up at [uptimerobot.com](https://uptimerobot.com) (free tier: 50 monitors, 5-min intervals)
2. Add monitor:
   - Type: HTTPS
   - URL: `https://api.morgenruf.dev/healthz`
   - Name: Morgenruf API
   - Interval: 5 minutes
3. Create a Status Page in UptimeRobot dashboard
4. Set custom domain: `status.morgenruf.dev`
5. Add CNAME in your DNS: `status.morgenruf.dev` → `stats.uptimerobot.com`

## Status Badge

Add to README:
```markdown
[![Uptime](https://img.shields.io/uptimerobot/ratio/YOUR_MONITOR_ID)](https://status.morgenruf.dev)
```
