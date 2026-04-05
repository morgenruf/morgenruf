# Privacy Policy — Morgenruf

**Effective date:** April 5, 2026 · **Last updated:** April 5, 2026

Morgenruf ("we", "our", "us") operates the Slack application Morgenruf and the website at morgenruf.dev. This Privacy Policy explains what personal data we collect, why we collect it, how we use and protect it, and what rights you have.

---

## 1. Who We Are

Morgenruf is an open-source Slack standup bot. The hosted cloud version is operated by the Morgenruf project. The source code is publicly available at [github.com/morgenruf/morgenruf](https://github.com/morgenruf/morgenruf) under the MIT license.

For privacy inquiries: **privacy@morgenruf.dev**

---

## 2. Data We Collect

### 2.1 When You Install Morgenruf (Cloud Version)

| Data | Source | Purpose |
|------|--------|---------|
| Slack workspace ID and name | Slack OAuth | Identify your workspace |
| Slack bot token and signing secret | Slack OAuth | Authenticate API calls |
| Slack user IDs and display names | Slack API | Send DMs, display in dashboard |
| Email addresses (if scope granted) | Slack API | Transactional emails |
| User timezones | Slack API | Schedule standups correctly |
| Standup responses (text) | Users via bot DM | Core functionality |
| Standup configuration (schedule, channel, questions) | Admin via dashboard | Core functionality |
| Kudos messages and recipients | Users via Slack | Kudos/recognition feature |
| Mood ratings (1–5, optional) | Users via bot DM | Mood analytics |
| IP addresses and request logs | Hosting infrastructure | Security and debugging |

### 2.2 What We Do NOT Collect

- We do **not** read any Slack messages outside of direct messages sent to the Morgenruf bot.
- We do **not** collect payment information (the service is free).
- We do **not** track users across other websites.

### 2.3 Self-Hosted Deployments

If you self-host Morgenruf, you operate as the data controller. We have no access to your data. Your data stays entirely on your own infrastructure.

---

## 3. How We Use Your Data

We use collected data exclusively to:

- Deliver standup prompts to team members at scheduled times
- Post formatted standup summaries to your configured Slack channel
- Display analytics (participation rates, history) in the web dashboard
- Send transactional emails: installation confirmation, weekly digest, inactive-member nudges
- Generate AI-powered standup summaries (only if you enable the AI summary feature; see §5)
- Debug errors and maintain service reliability via Sentry error monitoring
- Enforce security (rate limiting, CSRF protection, SSRF blocking)

We do **not** use your data for advertising, profiling, or selling to third parties.

---

## 4. Legal Basis for Processing (GDPR)

For users in the European Economic Area (EEA), we process data under the following legal bases:

| Processing activity | Legal basis |
|---------------------|-------------|
| Delivering standup prompts and summaries | Performance of contract (Art. 6(1)(b) GDPR) |
| Analytics and dashboard | Legitimate interests (Art. 6(1)(f) GDPR) |
| Transactional emails | Performance of contract / Legitimate interests |
| AI summary (opt-in) | Consent (Art. 6(1)(a) GDPR) |
| Security logging | Legitimate interests |

---

## 5. Third-Party Services (Sub-Processors)

### Always Active
| Sub-processor | Purpose | Location | Privacy Policy |
|---------------|---------|----------|----------------|
| Slack Technologies (Salesforce) | Slack API — message delivery | USA/EU | [slack.com/privacy](https://slack.com/privacy) |
| Railway.app | Database and application hosting | USA | [railway.app/legal/privacy](https://railway.app/legal/privacy) |
| Resend | Transactional email delivery | USA | [resend.com/legal/privacy-policy](https://resend.com/legal/privacy-policy) |
| Netlify | Website hosting (morgenruf.dev) | USA | [netlify.com/privacy](https://www.netlify.com/privacy/) |
| Sentry | Error monitoring (stack traces, no standup content) | USA | [sentry.io/privacy](https://sentry.io/privacy/) |

### Optional (Only If You Enable AI Summaries)
| Sub-processor | Purpose | Location | Privacy Policy |
|---------------|---------|----------|----------------|
| OpenAI | GPT-4o-mini standup summarisation | USA | [openai.com/policies/privacy-policy](https://openai.com/policies/privacy-policy) |
| Anthropic | Claude Haiku standup summarisation | USA | [anthropic.com/privacy](https://www.anthropic.com/privacy) |

**Important:** If you enable AI summaries, standup response text is sent to the selected AI provider to generate the summary. The text contains whatever your team members write in their standups. OpenAI and Anthropic process this data under their API terms — they do **not** use API data for model training by default. You can disable AI summaries at any time in the workspace settings.

We do not share data with any other third parties.

---

## 6. Data Retention

| Data type | Retention period |
|-----------|-----------------|
| Standup responses | 90 days (auto-deleted) |
| Analytics aggregates | 12 months |
| Slack tokens | Until you uninstall Morgenruf |
| Request/error logs | 30 days |
| Email send logs | 90 days |

You can request earlier deletion at any time (see §8).

---

## 7. Data Storage and Security

- All data is stored in a PostgreSQL database hosted on **Railway.app** in the United States.
- All data in transit is encrypted via **TLS/HTTPS**.
- Slack bot tokens are stored **encrypted at rest** using AES-256.
- Sessions are backed by **Redis** with expiry.
- We follow Slack's security best practices including signing secret validation on every event.
- Access to production systems is restricted to authorised contributors.
- We conduct periodic security reviews of infrastructure.

---

## 8. Your Rights

Depending on your location, you may have the following rights:

- **Access** — request a copy of the data we hold about your workspace.
- **Rectification** — ask us to correct inaccurate data.
- **Erasure ("right to be forgotten")** — request deletion of all workspace data.
- **Data portability** — receive your standup data in CSV format (also available via dashboard export).
- **Restriction** — ask us to pause processing while a dispute is resolved.
- **Objection** — object to processing based on legitimate interests.
- **Withdraw consent** — if you enabled AI summaries, you can disable them at any time.

**To exercise any right:** Email privacy@morgenruf.dev with your Slack workspace ID (visible in your Slack URL: `https://app.slack.com/client/TXXXXXXXX`). We will respond within **30 days**.

**EEA users:** You have the right to lodge a complaint with your national data protection authority (e.g., DPA in your country).

---

## 9. Data Deletion

To delete all your workspace data:

1. **Uninstall Morgenruf** from your Slack workspace (`Manage Apps` → Remove Morgenruf). We will automatically delete all workspace data within 30 days of receiving the uninstall event from Slack.
2. **Immediate deletion:** Email privacy@morgenruf.dev with your Slack team ID for immediate deletion.
3. **Self-hosted:** Simply drop your database or run the provided cleanup script.

---

## 10. International Data Transfers

Our hosting is based in the United States. If you are located in the EEA or UK, data is transferred to the USA. We rely on Standard Contractual Clauses (SCCs) and the adequacy frameworks of our sub-processors for these transfers. You can request a copy of applicable transfer mechanisms by emailing privacy@morgenruf.dev.

---

## 11. Children's Privacy

Morgenruf is not directed at children under 13. We do not knowingly collect personal data from children. If you believe a child has provided us data, please contact privacy@morgenruf.dev.

---

## 12. Changes to This Policy

We may update this policy to reflect product changes or legal requirements. For material changes, we will notify workspace admins via Slack DM at least 14 days before the change takes effect. Continued use after the effective date constitutes acceptance of the updated policy. The latest version is always at morgenruf.dev/privacy.

---

## 13. Contact

**Privacy questions:** privacy@morgenruf.dev  
**General support:** hello@morgenruf.dev  
**GitHub Issues:** [github.com/morgenruf/morgenruf/issues](https://github.com/morgenruf/morgenruf/issues)

---

*This policy applies to the Morgenruf hosted cloud service. If you self-host Morgenruf, you are the data controller and this policy does not apply to your deployment.*
