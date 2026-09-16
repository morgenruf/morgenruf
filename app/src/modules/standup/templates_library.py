"""Standup question templates library."""

TEMPLATES = [
    {
        "id": "daily-standup",
        "name": "Daily Standup",
        "icon": "☀️",
        "description": "Classic async daily standup — yesterday, today, blockers.",
        "questions": [
            "What did you complete yesterday?",
            "What are you working on today?",
            "Any blockers or impediments?",
        ],
    },
    {
        "id": "weekly-goals",
        "name": "Weekly Goals Check-in",
        "icon": "🎯",
        "description": "Monday goal-setting + Friday wrap-up in one.",
        "questions": [
            "What are your top 3 priorities this week?",
            "What did you accomplish last week?",
            "What might get in your way this week?",
        ],
    },
    {
        "id": "engineering",
        "name": "Engineering Team",
        "icon": "⚙️",
        "description": "Focused on PRs, code reviews, and technical blockers.",
        "questions": [
            "What PRs did you merge or review yesterday?",
            "What are you coding or reviewing today?",
            "Any technical blockers, dependencies, or waiting on reviews?",
        ],
    },
    {
        "id": "design",
        "name": "Design Team",
        "icon": "🎨",
        "description": "Design-focused check-in with feedback and delivery tracking.",
        "questions": [
            "What designs did you complete or hand off yesterday?",
            "What are you designing or iterating on today?",
            "Any feedback needed or blockers from stakeholders?",
        ],
    },
    {
        "id": "sales",
        "name": "Sales Pipeline",
        "icon": "💼",
        "description": "Sales-focused — deals, calls, and pipeline health.",
        "questions": [
            "What deals did you advance or close yesterday?",
            "What calls, demos, or outreach do you have today?",
            "Any deals at risk or support needed from the team?",
        ],
    },
    {
        "id": "marketing",
        "name": "Marketing Team",
        "icon": "📣",
        "description": "Campaign progress, content, and launch tracking.",
        "questions": [
            "What campaigns or content did you ship yesterday?",
            "What are you launching or creating today?",
            "Any approvals, assets, or dependencies you're waiting on?",
        ],
    },
    {
        "id": "product",
        "name": "Product Management",
        "icon": "🗺️",
        "description": "Roadmap, discovery, and stakeholder alignment.",
        "questions": [
            "What spec, research, or decision did you finish yesterday?",
            "What are you defining, prioritising, or aligning on today?",
            "Any open questions or blockers blocking a decision?",
        ],
    },
    {
        "id": "customer-success",
        "name": "Customer Success",
        "icon": "🤝",
        "description": "Accounts, renewals, and customer health.",
        "questions": [
            "Which customers did you touch base with yesterday?",
            "What calls, QBRs, or follow-ups do you have today?",
            "Any at-risk accounts or escalations the team should know about?",
        ],
    },
    {
        "id": "sprint-review",
        "name": "Sprint Review",
        "icon": "🏃",
        "description": "End-of-sprint: what shipped, what didn't, retro notes.",
        "questions": [
            "What did your team ship this sprint?",
            "What was not completed and why?",
            "What would you do differently next sprint?",
        ],
    },
    {
        "id": "retrospective",
        "name": "Sprint Retrospective",
        "icon": "🔁",
        "description": "Start / Stop / Continue retro format.",
        "questions": [
            "What should we START doing?",
            "What should we STOP doing?",
            "What should we CONTINUE doing?",
        ],
    },
    {
        "id": "okr-checkin",
        "name": "OKR Check-in",
        "icon": "📊",
        "description": "Weekly OKR progress — key result updates.",
        "questions": [
            "Which key results did you move forward this week?",
            "What's your confidence level on hitting your OKRs? (1–10)",
            "What's the biggest risk to your OKRs right now?",
        ],
    },
    {
        "id": "incident-review",
        "name": "Incident / On-Call",
        "icon": "🚨",
        "description": "Post-incident or on-call handoff format.",
        "questions": [
            "What incidents or alerts did you handle yesterday?",
            "What are you monitoring or investigating today?",
            "Any ongoing incidents, known issues, or risk areas?",
        ],
    },
    {
        "id": "onboarding",
        "name": "New Hire Onboarding",
        "icon": "👋",
        "description": "Daily check-in for new team members during onboarding.",
        "questions": [
            "What did you learn or set up yesterday?",
            "What onboarding task or meeting do you have today?",
            "What questions do you have or where do you feel stuck?",
        ],
    },
    {
        "id": "data-analytics",
        "name": "Data & Analytics",
        "icon": "📈",
        "description": "Data pipelines, dashboards, and insight delivery.",
        "questions": [
            "What analysis, pipeline, or dashboard did you complete yesterday?",
            "What data work are you doing today?",
            "Any data quality issues, access blockers, or stakeholder dependencies?",
        ],
    },
    {
        "id": "devops-platform",
        "name": "DevOps / Platform",
        "icon": "🛠️",
        "description": "Infra, deployments, and reliability work.",
        "questions": [
            "What infra changes or deployments did you complete yesterday?",
            "What are you deploying, migrating, or improving today?",
            "Any production issues, capacity concerns, or pending approvals?",
        ],
    },
    {
        "id": "security",
        "name": "Security Team",
        "icon": "🔒",
        "description": "Vulnerability, compliance, and security review tracking.",
        "questions": [
            "What security reviews, patches, or assessments did you complete?",
            "What are you auditing, hardening, or responding to today?",
            "Any open vulnerabilities, compliance deadlines, or escalations?",
        ],
    },
    {
        "id": "leadership",
        "name": "Leadership / Exec",
        "icon": "🏢",
        "description": "High-level weekly leadership sync.",
        "questions": [
            "What did your team accomplish this week?",
            "What are your team's top priorities next week?",
            "What do you need from leadership or other teams?",
        ],
    },
    {
        "id": "remote-team",
        "name": "Remote / Async Team",
        "icon": "🌍",
        "description": "Timezone-friendly async update with context.",
        "questions": [
            "What did you complete in your last work session?",
            "What will you focus on in your next work session?",
            "Anything the team needs to know (decisions, blockers, FYIs)?",
        ],
    },
    {
        "id": "1on1",
        "name": "1:1 Check-in",
        "icon": "💬",
        "description": "Manager–report 1:1 async prep.",
        "questions": [
            "What went well this week?",
            "What was challenging or frustrating?",
            "What support or feedback do you need from me?",
        ],
    },
    {
        "id": "support",
        "name": "Customer Support",
        "icon": "🎧",
        "description": "Support ticket volume, escalations, and knowledge gaps.",
        "questions": [
            "What tickets did you resolve or escalate yesterday?",
            "What's your ticket queue or focus today?",
            "Any recurring issues, missing docs, or product bugs to flag?",
        ],
    },
    {
        "id": "qa",
        "name": "QA / Testing",
        "icon": "🧪",
        "description": "Test coverage, bug tracking, and release readiness.",
        "questions": [
            "What test cases or bugs did you resolve yesterday?",
            "What are you testing or validating today?",
            "Any blocking bugs, flaky tests, or release risks?",
        ],
    },
    {
        "id": "finance",
        "name": "Finance Team",
        "icon": "💰",
        "description": "Finance ops, reporting, and approvals.",
        "questions": [
            "What financial reports or approvals did you process yesterday?",
            "What are your key tasks or deadlines today?",
            "Any budget concerns, pending approvals, or compliance issues?",
        ],
    },
    {
        "id": "content",
        "name": "Content & Editorial",
        "icon": "✍️",
        "description": "Content pipeline, publishing, and editorial calendar.",
        "questions": [
            "What content did you publish or draft yesterday?",
            "What are you writing, editing, or publishing today?",
            "Any deadlines, approvals, or asset dependencies blocking you?",
        ],
    },
    {
        "id": "research",
        "name": "Research & UX",
        "icon": "🔬",
        "description": "User research, usability studies, and insight synthesis.",
        "questions": [
            "What research, interviews, or synthesis did you complete yesterday?",
            "What research activities are you running today?",
            "Any open questions, recruitment blockers, or stakeholder reviews needed?",
        ],
    },
    {
        "id": "personal",
        "name": "Personal Productivity",
        "icon": "🧘",
        "description": "Individual daily planning — goals, energy, and focus.",
        "questions": [
            "What's your biggest win from yesterday?",
            "What is the ONE most important thing to accomplish today?",
            "What might derail you, and how will you handle it?",
        ],
    },
]


def get_template(template_id: str) -> dict | None:
    """Return a template by id, or None."""
    return next((t for t in TEMPLATES if t["id"] == template_id), None)
