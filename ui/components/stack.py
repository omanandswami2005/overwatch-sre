"""The 5-service stack this UI sits in front of — condensed from
docker-compose.yml so a visitor understands the whole system topology
without leaving this screen.
"""

import streamlit as st

_SERVICES = [
    ("target-app", "8080", "the demo service — on-demand failure injection (/crash /leak /slow)"),
    ("prometheus", "9090", "scrapes target-app + cadvisor every 5s"),
    ("cadvisor", "8081", "container-level CPU/memory metrics"),
    ("backend", "8000", "the Claude tool-use agent, the human-gated restart, the audit log"),
    ("ui", "8501", "this console — a pure HTTP client, no logic of its own"),
]


def render() -> None:
    st.markdown('<div class="section-label">what\'s running</div>', unsafe_allow_html=True)
    cards = "".join(
        f"""<div class="feature-card">
        <span class="feature-port">:{port}</span>
        <div class="feature-name">{name}</div>
        <div class="feature-desc">{desc}</div>
        </div>"""
        for name, port, desc in _SERVICES
    )
    st.markdown(f'<div class="feature-grid">{cards}</div>', unsafe_allow_html=True)
