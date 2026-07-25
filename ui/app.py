import requests
import streamlit as st

BACKEND_URL = "http://backend:8000"

st.set_page_config(page_title="Overwatch-SRE", page_icon="🩺", layout="centered")

# tokens + type from UI-DESIGN.md — see that doc before changing colors/fonts.
STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; }
code, pre { font-family: 'JetBrains Mono', monospace; }

.vitals-strip { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 1rem;
  background: #121821; border-radius: 8px; margin-bottom: 1rem; }
.vitals-dot { height: 10px; width: 10px; border-radius: 50%; display: inline-block; }
.vitals-dot.healthy { background: #35D0A6; box-shadow: 0 0 8px #35D0A6; }
.vitals-dot.degraded { background: #F5A623; box-shadow: 0 0 8px #F5A623; animation: pulse 1.2s infinite; }
.vitals-dot.down { background: #E4483C; box-shadow: 0 0 8px #E4483C; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

st.markdown("### OVERWATCH · SRE COPILOT")

if "history" not in st.session_state:
    st.session_state.history = []


def fetch_audit():
    try:
        r = requests.get(f"{BACKEND_URL}/audit", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


audit_events = fetch_audit()

# --- vitals strip (signature element — see UI-DESIGN.md) ---
status, label = "healthy", "healthy"
if audit_events is None:
    status, label = "down", "backend unreachable"
elif audit_events:
    last = audit_events[-1]
    if last.get("type") == "ask" and last.get("recommended_action"):
        status, label = "degraded", "awaiting approval"
    elif last.get("type") == "approve" and last.get("result", {}).get("status") == "restarted":
        status, label = "healthy", "recovering"

st.markdown(
    f"""<div class="vitals-strip">
    <span class="vitals-dot {status}"></span>
    <span style="font-family:'JetBrains Mono',monospace;">target-app</span>
    <span style="color:#5B6672;">{label}</span>
    </div>""",
    unsafe_allow_html=True,
)

if audit_events is None:
    st.error("Can't reach the backend. Check `docker compose ps` and retry.")

# --- triage chat ---
if not st.session_state.history:
    st.info(
        "No incidents yet. Ask what's happening, or wait — "
        "Overwatch speaks up first if something breaks."
    )

for i, msg in enumerate(st.session_state.history):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg.get("recommended_action") and msg.get("action_id") and not msg.get("resolved"):
            with st.container(border=True):
                st.markdown("**ROOT CAUSE / RECOMMENDED ACTION**")
                st.code(f"restart_container: {msg['recommended_action']['container']}", language=None)
                c1, c2 = st.columns(2)
                if c1.button("Approve restart", key=f"approve-{msg['action_id']}"):
                    try:
                        r = requests.post(f"{BACKEND_URL}/approve/{msg['action_id']}", timeout=15)
                        r.raise_for_status()
                        result = r.json()
                        st.success(f"Restarted {result.get('container', 'target-app')}.")
                    except Exception as exc:
                        st.error(f"Approve failed: {exc}")
                    st.session_state.history[i]["resolved"] = True
                    st.rerun()
                if c2.button("Dismiss", key=f"dismiss-{msg['action_id']}"):
                    st.session_state.history[i]["resolved"] = True
                    st.rerun()

question = st.chat_input("Ask about the system...")
if question:
    st.session_state.history.append({"role": "user", "content": question})
    try:
        r = requests.post(f"{BACKEND_URL}/ask", json={"question": question}, timeout=95)
        r.raise_for_status()
        data = r.json()
        st.session_state.history.append(
            {
                "role": "assistant",
                "content": data["answer"],
                "recommended_action": data.get("recommended_action"),
                "action_id": data.get("action_id"),
                "resolved": False,
            }
        )
    except Exception as exc:
        st.session_state.history.append(
            {"role": "assistant", "content": f"Can't reach the backend: {exc}"}
        )
    st.rerun()

# --- audit drawer ---
with st.expander(f"audit trail ({len(audit_events or [])} events)"):
    for event in (audit_events or [])[::-1]:
        st.code(str(event), language=None)
