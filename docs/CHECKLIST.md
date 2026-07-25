# Checklist — who's building what

**Claim rule (keep it light):** before you start a task, put your name on its line and commit that one-line edit (`chore: claim A-1`) so nobody doubles up. Check it off with a short commit message when done. That's the whole protocol — no branches-per-item ceremony needed for a 6-hour build; commit to `main` directly unless you're mid-breakage.

## Lanes (work in parallel, don't touch other lanes' files)

| Lane | Owns | Files |
|---|---|---|
| A | Target app + failure injection + Prometheus/cAdvisor wiring | `target-app/`, `docker-compose.yml` (metrics services) |
| B | Backend: FastAPI + custom Claude tool-use agent, restart logic, audit log | `backend/Dockerfile`, `backend/app.py` |
| C | Streamlit UI + demo polish | `ui/` |

Lane B ships an HTTP API — this is the contract Lane C builds against (agree the shape now, before both start):
- `POST /ask {question}` → `{answer, recommended_action, action_id}`
- `POST /approve/{action_id}` → `{status, result}`
- `GET /audit` → list of logged entries

Lane C can build the full chat + approve flow against a hardcoded fixture matching this shape while Lane B is still wiring the real thing.

## Tasks

**Wave 0 — fully parallel, start now**
- [x] A-1 target-app skeleton (FastAPI): `/crash`, `/leak`, `/slow`, `/metrics` — _(owner: )_
- [x] A-2 `docker-compose.yml` with all 5 services (prometheus + cadvisor + target-app + backend + ui) — _(owner: )_
- [x] B-1 `backend/Dockerfile`: plain `python:3.11-slim` + `uv pip install -r requirements.txt` (use `uv`, not `pip`, everywhere) — _(owner: )_
- [x] B-2 `ANTHROPIC_API_KEY`, `PROMETHEUS_URL`, `ANTHROPIC_MODEL` read from env in `backend/app.py` — _(owner: )_
- [x] C-1 Streamlit skeleton with chat box + Approve/Deny button — _(owner: )_

**Wave 1 — after Wave 0 contracts land**
- [x] A-3 confirmed Prometheus scrapes target-app + cadvisor — both show `health: up` at `/api/v1/targets` — _(owner: )_
- [x] B-3 tool schemas defined in `backend/app.py`: `query_prometheus`, `get_container_status`, `get_container_logs` (read-only) + `propose_restart` (records a recommendation only, never restarts) — _(owner: )_
- [x] B-4 `POST /ask`: Claude tool-use loop (Anthropic Messages API, `_run_agent` in `backend/app.py`) — _(owner: )_
- [x] B-5 `POST /approve/{action_id}`: docker-py `restart`, only runs on this call — _(owner: )_
- [x] B-6 `GET /audit` + append every question/diagnosis/approval/action to `audit-log.jsonl` — _(owner: )_
- [x] C-2 Streamlit wired to real backend `/ask` (no fixture) — _(owner: )_
- [x] C-3 Approve/Dismiss buttons wired to backend `/approve/{action_id}` — _(owner: )_

**Wave 2 — integration**
- [x] D-1 end-to-end run verified for all three failure modes: `/leak`, `/slow`, `/crash` —
  ask copilot, (for `/leak`/`/crash`) approve restart, confirm recovery — _(owner: )_
- [x] D-2 rehearsed demo script from README against `/leak` — matches step-for-step — _(owner: )_

## Demo-ready gate (all must pass)
- [x] Failure injection reliably reproduces on demand — `/leak`, `/slow`, `/crash` all tested
- [x] Copilot correctly names the root cause unprompted — memory leak (cites `app_leak_bytes` +
  OOM log lines), injected latency (cites log line, correctly declines to recommend a restart
  since it's self-resolving), crash (cites exit code + FATAL log line)
- [x] Restart action is blocked until Approve is clicked, and works after — verified for both
  the leak and crash scenarios; `/slow` correctly gets no restart proposal at all
- [x] `audit-log.jsonl` shows the full trail for the demo run — `ask`/`approve` pairs present
  with `ts`, question, answer, and result for each
