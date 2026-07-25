"""Triage chat: message history, inline diagnosis card, chat input handling."""

import streamlit as st

from api import approve, ask

_ACTION_VERBS = {"restart_container": "restart_container", "rollback_container": "rollback_container"}


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
            if msg.get("source") == "watcher":
                st.caption(":mag: noticed by the proactive watcher — nobody asked this")
            if msg.get("recommended_action") and msg.get("action_id") and not msg.get("resolved"):
                _render_diagnosis_card(history, i, msg)


def _render_diagnosis_card(history: list[dict], i: int, msg: dict) -> None:
    action = msg["recommended_action"]
    verb = _ACTION_VERBS.get(action.get("type"), action.get("type", "restart_container"))
    with st.container(border=True):
        label = "ROLLBACK NEEDED" if verb == "rollback_container" else "RECOMMENDED ACTION"
        st.markdown(f"**{label}**")
        st.code(f"{verb}({action['container']})", language=None)
        reason = action.get("reason")
        if reason:
            st.caption(reason)
        approve_label = "Approve rollback" if verb == "rollback_container" else "Approve restart"
        c1, c2 = st.columns(2)
        if c1.button(approve_label, key=f"approve-{msg['action_id']}"):
            try:
                result = approve(msg["action_id"])
                status = result.get("status")
                if status in ("no_previous_image", "previous_image_found_not_executed"):
                    st.warning(result.get("message", status))
                elif status == "failed":
                    st.error(f"Failed: {result.get('error', 'unknown error')}")
                else:
                    st.success(f"{status.capitalize()} {result.get('container', action['container'])}.")
            except Exception as exc:
                st.error(f"Approve failed: {exc}")
            history[i]["resolved"] = True
            st.rerun()
        if c2.button("Dismiss", key=f"dismiss-{msg['action_id']}"):
            history[i]["resolved"] = True
            st.session_state.setdefault("dismissed_action_ids", set()).add(msg["action_id"])
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


def sync_pending_incidents(history: list[dict], incidents: list[dict] | None) -> None:
    """Pulls in any unapproved proposal from ANY source (watcher, Slack bot,
    scripts/demo-trigger.sh, or this same chat in a different session) that
    isn't already visible here — this is the fix for "I have to ask a question
    before I see anything to approve": a watcher-triggered proposal previously
    only showed up in the backend audit log/Slack, never as an actionable card
    in this console unless the user happened to type something first.
    """
    if not incidents:
        return
    known_ids = {msg.get("action_id") for msg in history if msg.get("action_id")}
    dismissed = st.session_state.get("dismissed_action_ids", set())
    for incident in incidents:
        action_id = incident["action_id"]
        if incident["approved"] or action_id in known_ids or action_id in dismissed:
            continue
        if not incident.get("actionable"):
            # proposed before the backend last restarted - _pending_actions no
            # longer has it, so Approve would just 404. Not worth surfacing as
            # a dead-end card; it stays visible in the audit trail instead.
            continue
        history.append(
            {
                "role": "assistant",
                "content": incident["answer"],
                "recommended_action": incident["recommended_action"],
                "action_id": action_id,
                "source": incident.get("source"),
                "resolved": False,
            }
        )
