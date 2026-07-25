"""The / route — the pitch. Hero, how it works, watcher/librarian, the
hard rule, what's running, try it, and the why-these-choices/verified
footer. No chat, no audit drawer — that's all on /main now.

MAIN_PAGE is set by app.py after both st.Page objects exist (it can't be
known at import time since the two views reference each other).
"""

import streamlit as st

from api import fetch_audit
from components import footer, landing, vitals

MAIN_PAGE = None


def render() -> None:
    if "pulse_tick" not in st.session_state:
        st.session_state.pulse_tick = 0
    st.session_state.pulse_tick += 1

    audit_events = fetch_audit()
    status, _ = vitals.vitals_status(audit_events)

    landing.render(status, st.session_state.pulse_tick)

    if MAIN_PAGE is not None:
        st.page_link(MAIN_PAGE, label="Launch the console", icon=":material/arrow_forward:")

    footer.render()
