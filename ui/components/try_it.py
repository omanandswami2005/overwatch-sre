"""The CTA panel — the README demo script, made directly actionable from
this screen. The /leak link is a plain browser hyperlink to target-app's
exposed host port; the UI still issues no requests of its own beyond
api.py's calls to the backend.
"""

TARGET_APP_URL = "http://localhost:8080"

_STEPS = [
    "Trigger a failure on target-app — the button below grows its memory a few "
    "chunks at a time.",
    'Ask below: <em>"why is target-app unhealthy?"</em> — or just wait, the watcher '
    "checks every 30s and will speak up first if it trips before you ask.",
    "Review the recommended action, then <strong>Approve restart</strong>.",
    "Open <strong>audit trail</strong> below the chat to see the full record.",
]


def html() -> str:
    steps_html = "".join(
        f"""<div class="cta-step"><span class="cta-step-num">{i:02d}</span><span>{step}</span></div>"""
        for i, step in enumerate(_STEPS, start=1)
    )
    return f"""<div class="cta-panel">
    <div class="cta-label">try it</div>
    <div class="cta-steps">{steps_html}</div>
    <a class="cta-button" href="{TARGET_APP_URL}/leak" target="_blank" rel="noopener">
      trigger a leak &#8599;
    </a>
    </div>"""
