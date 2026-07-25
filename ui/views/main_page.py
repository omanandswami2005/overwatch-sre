"""The /main route — the actual testing console. Vitals strip, triage
chat, diagnosis card, audit drawer. No landing copy here; that's on /.

LANDING_PAGE is set by app.py after both st.Page objects exist.
"""

import streamlit as st

from api import fetch_audit
from components import audit_drawer, chat, vitals

LANDING_PAGE = None
DOCS_PAGE = None


def render() -> None:
    nav = st.columns([1, 1, 6])
    if LANDING_PAGE is not None:
        nav[0].page_link(LANDING_PAGE, label="About", icon=":material/arrow_back:")
    if DOCS_PAGE is not None:
        nav[1].page_link(DOCS_PAGE, label="Architecture", icon=":material/schema:")

    if "history" not in st.session_state:
        st.session_state.history = []
    if "pulse_tick" not in st.session_state:
        st.session_state.pulse_tick = 0
    st.session_state.pulse_tick += 1

    audit_events = fetch_audit()
    status, label = vitals.vitals_status(audit_events)

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)
    vitals.render_strip(status, label, st.session_state.pulse_tick)

    if audit_events is None:
        st.error("Can't reach the backend. Check `docker compose ps` and retry.")

    chat.render_history(st.session_state.history)
    chat.handle_input(st.session_state.history)

    audit_drawer.render(audit_events)
