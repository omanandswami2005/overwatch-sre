"""Triage chat: message history, inline diagnosis card, chat input handling."""

import streamlit as st

from api import approve, ask


def render_history(history: list[dict]) -> None:
    if not history:
        st.info(
            "No incidents yet. Ask what's happening, or wait — "
            "Overwatch speaks up first if something breaks."
        )
        return

    for i, msg in enumerate(history):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("recommended_action") and msg.get("action_id") and not msg.get("resolved"):
                _render_diagnosis_card(history, i, msg)


def _render_diagnosis_card(history: list[dict], i: int, msg: dict) -> None:
    with st.container(border=True):
        st.markdown("**RECOMMENDED ACTION**")
        st.code(f"restart_container({msg['recommended_action']['container']})", language=None)
        reason = msg["recommended_action"].get("reason")
        if reason:
            st.caption(reason)
        c1, c2 = st.columns(2)
        if c1.button("Approve restart", key=f"approve-{msg['action_id']}"):
            try:
                result = approve(msg["action_id"])
                st.success(f"Restarted {result.get('container', 'target-app')}.")
            except Exception as exc:
                st.error(f"Approve failed: {exc}")
            history[i]["resolved"] = True
            st.rerun()
        if c2.button("Dismiss", key=f"dismiss-{msg['action_id']}"):
            history[i]["resolved"] = True
            st.rerun()


def handle_input(history: list[dict]) -> None:
    question = st.chat_input("Ask about the system...")
    if not question:
        return
    history.append({"role": "user", "content": question})
    try:
        data = ask(question)
        history.append(
            {
                "role": "assistant",
                "content": data["answer"],
                "recommended_action": data.get("recommended_action"),
                "action_id": data.get("action_id"),
                "resolved": False,
            }
        )
    except Exception as exc:
        history.append({"role": "assistant", "content": f"Can't reach the backend: {exc}"})
    st.rerun()
