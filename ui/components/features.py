"""Feature highlight grid — right after the hero, before "how it works".
Judges scan for 5 seconds before deciding whether to read further; this is
the "what's actually in here" summary, each claim tied to a real file so
it's checkable, not marketing copy.
"""

_FEATURES = [
    ("LLM wiki", "backend/librarian.py", "A second, isolated agent documents every resolved incident into a self-updating wiki — the chat agent cites it by ID on repeat symptoms."),
    ("Memory + escalation", "backend/app.py", "The agent checks incident history before proposing anything. A 2nd+ occurrence gets flagged as recurring and escalated, not treated as fresh."),
    ("Runbook", "backend/runbook.md", "Human-authored, codified steps per failure type — read-only reference the agent checks before deciding what to propose."),
    ("Rollback detection", "backend/toolsets/remediation_toolset.py", "Recognizes a crash loop (restart already tried, didn't help) and proposes a rollback instead of blindly repeating the same fix."),
    ("Proactive watcher", "backend/watcher.py", "Cheap checks every 30s, no LLM call unless one trips — the copilot notices problems before anyone asks."),
    ("Tracing + dashboards", "jaeger, grafana", "OpenTelemetry traces + a real Grafana dashboard with restart annotations, not just metrics."),
    ("Slack", "slack-bot/, backend/notifications.py", "A full second interface (/overwatch in Slack, Socket Mode) plus proposal/outcome notifications — not just a webhook ping."),
    ("Incident reports", "backend/reports.py", "Haiku compresses raw history, Sonnet writes a 7-section postmortem — Markdown + downloadable PDF, generated on demand."),
    ("Multi-service", "target-app + worker-service", "Watches two services with genuinely different failure signatures (memory leak vs. stuck queue) — not two copies of the same demo app."),
]


def html() -> str:
    cards = "".join(
        f"""<div class="feature-card">
        <span class="feature-port">{path}</span>
        <div class="feature-name">{name}</div>
        <div class="feature-desc">{desc}</div>
        </div>"""
        for name, path, desc in _FEATURES
    )
    return f'<div><div class="section-label">what\'s actually in here</div><div class="feature-grid">{cards}</div></div>'
