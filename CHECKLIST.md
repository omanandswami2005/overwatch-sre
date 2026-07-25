# Checklist — who's building what

**Claim rule (keep it light):** before you start a task, put your name on its line and commit that one-line edit (`chore: claim A-1`) so nobody doubles up. Check it off with a short commit message when done. That's the whole protocol — no branches-per-item ceremony needed for a 6-hour build; commit to `main` directly unless you're mid-breakage.

## Lanes (work in parallel, don't touch other lanes' files)

| Lane | Owns | Files |
|---|---|---|
| A | Target app + failure injection + Prometheus/cAdvisor wiring | `target-app/`, `docker-compose.yml` (metrics services) |
| B | Backend: extended Holmes+FastAPI image, custom toolset, restart logic, audit log | `backend/Dockerfile`, `backend/app.py`, `backend/toolsets/` |
| C | Streamlit UI + demo polish | `ui/` |

Lane B ships an HTTP API — this is the contract Lane C builds against (agree the shape now, before both start):
- `POST /ask {question}` → `{answer, recommended_action, action_id}`
- `POST /approve/{action_id}` → `{status, result}`
- `GET /audit` → list of logged entries

Lane C can build the full chat + approve flow against a hardcoded fixture matching this shape while Lane B is still wiring the real thing.

## Tasks

**Wave 0 — fully parallel, start now**
- [ ] A-1 target-app skeleton (FastAPI): `/crash`, `/leak`, `/slow`, `/metrics` — _(owner: )_
- [ ] A-2 `docker-compose.yml` skeleton with prometheus + cadvisor — _(owner: )_
- [ ] B-1 `backend/Dockerfile`: `FROM robustadev/holmes:0.36.0` + `apk add docker-cli` + `uv pip install fastapi uvicorn` (use `uv`, not `pip`, everywhere) — _(owner: )_
- [ ] B-2 `config.yaml`: `prometheus_url`, `ANTHROPIC_API_KEY` wired — _(owner: )_
- [ ] C-1 Streamlit skeleton with chat box + Approve/Deny button (against the fixture API shape above) — _(owner: )_

**Wave 1 — after Wave 0 contracts land**
- [ ] A-3 confirm Prometheus scrapes target-app + container metrics — _(owner: )_
- [ ] B-3 custom toolset YAML: recommend-only, no write tools given to Holmes — _(owner: )_
- [ ] B-4 `POST /ask`: FastAPI route calls `holmes ask` via subprocess, parses response — _(owner: )_
- [ ] B-5 `POST /approve/{action_id}`: docker-py `restart`, only runs on this call — _(owner: )_
- [ ] B-6 `GET /audit` + append every question/diagnosis/approval/action to `audit-log.jsonl` — _(owner: )_
- [ ] C-2 wire Streamlit to real backend `/ask` instead of fixture — _(owner: )_
- [ ] C-3 wire Approve button to backend `/approve/{action_id}` — _(owner: )_

**Wave 2 — integration**
- [ ] D-1 end-to-end run: trigger `/leak`, ask copilot, approve restart, confirm recovery — _(owner: )_
- [ ] D-2 rehearse demo script from README — _(owner: )_

## Demo-ready gate (all must pass)
- [ ] Failure injection reliably reproduces on demand
- [ ] Copilot correctly names the root cause (memory leak / crash / slowness) unprompted
- [ ] Restart action is blocked until Approve is clicked, and works after
- [ ] `audit-log.jsonl` shows the full trail for the demo run
