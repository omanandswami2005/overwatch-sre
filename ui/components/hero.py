"""The landing hero — product identity, live aggregate pulse, and a
credibility strip of real architectural facts (not vanity stats).

Extends UI-DESIGN.md's vitals-monitor thesis to the page's entry moment
("the app has a heartbeat and you're watching it") instead of reaching for
a generic marketing hero. The pulse line is driven by the same real,
audit-derived status as the vitals strip below it — never decorative.
Returns an HTML fragment; see components/landing.py for why this isn't
rendered via its own st.markdown() call.
"""

from .vitals import pulse_svg

_META = [
    "9 containers, 1 compose stack",
    "read-only diagnosis tools",
    "human-approved restarts only",
    "watches proactively, every 30s",
]


def html(status: str, tick: int) -> str:
    conn_state = "down" if status == "down" else "up"
    conn_label = "disconnected" if status == "down" else "connected"
    meta_chips = "".join(f'<span class="meta-chip">{m}</span>' for m in _META)
    return f"""<div class="hero">
    <span class="status-pill"><span class="status-dot {conn_state}"></span>{conn_label}</span>
    <div class="hero-eyebrow">on-call copilot</div>
    <div class="hero-wordmark">Overwatch <span class="hero-wordmark-sub">— Your SRE Copilot</span></div>
    <div class="hero-tagline">One chat window instead of four dashboards —
      diagnoses the system, proposes a fix, and only acts once you approve it.</div>
    <div class="hero-pulse">{pulse_svg(status, tick, width=760, height=48)}</div>
    <div class="meta-row">{meta_chips}</div>
    </div>"""
