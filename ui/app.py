import streamlit as st

import theme
from api import fetch_audit
from components import audit_drawer, chat, hero, how_it_works, stack, try_it, vitals

st.set_page_config(page_title="Overwatch-SRE", page_icon="🩺", layout="centered")
theme.inject()

if "history" not in st.session_state:
    st.session_state.history = []
if "pulse_tick" not in st.session_state:
    st.session_state.pulse_tick = 0
st.session_state.pulse_tick += 1

audit_events = fetch_audit()
status, label = vitals.vitals_status(audit_events)
tick = st.session_state.pulse_tick

hero.render(status, tick)
how_it_works.render()
stack.render()
try_it.render()
vitals.render_strip(status, label, tick)

if audit_events is None:
    st.error("Can't reach the backend. Check `docker compose ps` and retry.")

chat.render_history(st.session_state.history)
chat.handle_input(st.session_state.history)

audit_drawer.render(audit_events)
