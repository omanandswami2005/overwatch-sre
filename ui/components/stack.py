"""The service stack this UI sits in front of — condensed from
docker-compose.yml so a visitor understands the whole system topology
without leaving this screen.
"""

_SERVICES = [
    ("target-app", "8080", "the demo service — on-demand failure injection (/crash /leak /slow)"),
    ("worker-service", "8090", "second watched service — a stuck-queue failure signature, not a copy of target-app"),
    ("prometheus", "9090", "scrapes target-app + worker-service + cadvisor every 5s"),
    ("cadvisor", "8081", "container-level CPU/memory metrics"),
    ("jaeger", "16686", "distributed traces from target-app/worker-service, OpenTelemetry"),
    ("grafana", "3000", "real dashboard + restart annotations, anonymous viewer access"),
    ("backend", "8000", "the chat agent, the watcher, the librarian, the runbook, Slack "
     "notifications, the human-gated restart/rollback, and the audit log"),
    ("slack-bot", "—", "/overwatch slash command, Socket Mode — opt-in via --profile slack"),
    ("ui", "8501", "this console — a pure HTTP client, no logic of its own"),
]


def html() -> str:
    cards = "".join(
        f"""<div class="feature-card">
        <span class="feature-port">{":" + port if port != "—" else "opt-in"}</span>
        <div class="feature-name">{name}</div>
        <div class="feature-desc">{desc}</div>
        </div>"""
        for name, port, desc in _SERVICES
    )
    return f'<div><div class="section-label">what\'s running</div><div class="feature-grid">{cards}</div></div>'
