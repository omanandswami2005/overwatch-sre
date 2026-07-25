"""The propose -> approve -> execute -> audit loop, as a 4-step pipeline.

This is a real, order-dependent sequence (propose must precede approve,
approve must precede execute) — the numbering here encodes an actual
constraint of the system, not decoration.
"""

import streamlit as st

_STEPS = [
    ("ask", "You ask a plain-language question about system health."),
    ("diagnose", "Claude queries Prometheus metrics and container status/logs "
                 "(read-only) and names a root cause."),
    ("propose", "If a restart would plausibly fix it, that's recorded as a "
                "pending action. Nothing executes yet."),
    ("approve", "You click Approve restart — only then does the backend "
                "restart the container. Every step lands in audit-log.jsonl."),
]


def render() -> None:
    st.markdown('<div class="section-label">how it works</div>', unsafe_allow_html=True)
    cards = "".join(
        f"""<div class="step-card">
        <div class="step-index">{i:02d}</div>
        <div class="step-title">{title}</div>
        <div class="step-desc">{desc}</div>
        </div>"""
        for i, (title, desc) in enumerate(_STEPS, start=1)
    )
    st.markdown(f'<div class="step-row">{cards}</div>', unsafe_allow_html=True)
