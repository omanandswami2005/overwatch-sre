"""The CTA panel — the README demo script, made directly actionable from
this screen. Each trigger is a plain browser hyperlink to a watched
service's own exposed host port; the UI still issues no requests of its
own beyond api.py's calls to the backend.
"""

TARGET_APP_URL = "http://localhost:8080"
WORKER_SERVICE_URL = "http://localhost:8090"

_STEPS = [
    "Trigger a failure below — on target-app (memory leak, crash, slowness) or "
    "worker-service (a stuck queue — a different failure signature entirely).",
    'Ask below: <em>"why is target-app unhealthy?"</em> (or worker-service) — or '
    "just wait, the watcher checks every 30s and will speak up first if it trips "
    "before you ask.",
    "Review the recommended action, then <strong>Approve restart</strong>.",
    "Open <strong>audit trail</strong> below the chat to see the full record.",
]

_TRIGGERS = [
    ("trigger a leak", f"{TARGET_APP_URL}/leak"),
    ("trigger a crash", f"{TARGET_APP_URL}/crash"),
    ("trigger slowness", f"{TARGET_APP_URL}/slow"),
    ("jam worker-service", f"{WORKER_SERVICE_URL}/jam"),
]


def html() -> str:
    steps_html = "".join(
        f"""<div class="cta-step"><span class="cta-step-num">{i:02d}</span><span>{step}</span></div>"""
        for i, step in enumerate(_STEPS, start=1)
    )
    buttons_html = "".join(
        f'<a class="cta-button" href="{url}" target="_blank" rel="noopener">{label} &#8599;</a>'
        for label, url in _TRIGGERS
    )
    return f"""<div class="cta-panel">
    <div class="cta-label">try it</div>
    <div class="cta-steps">{steps_html}</div>
    <div style="display:flex; gap:0.6rem; flex-wrap:wrap;">{buttons_html}</div>
    </div>"""
