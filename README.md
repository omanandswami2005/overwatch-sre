# Overwatch-SRE

**What it is:** an LLM copilot that watches a small Dockerized app, answers questions about its health, diagnoses failures, and restarts a broken container — only after a human approves. One chat window instead of four dashboards. Built for a 6.5-hour hackathon.

**Ground rules satisfied:** Docker (Compose) + CNCF (Prometheus, graduated).

## What to build (4 pieces, nothing else)

1. **target-app** (FastAPI) — `/crash`, `/leak`, `/slow`, `/metrics`. The thing that breaks on demand.
2. **prometheus + cadvisor** — off-the-shelf compose services, config only, no code.
3. **backend** (FastAPI) — one container that: runs a small Claude tool-use agent loop (read-only tools: query Prometheus, get container status/logs; a `propose_restart` tool that only records a recommendation) for diagnosis, runs `docker restart <container>` via docker-py *only* when told to, and appends every step to `audit-log.jsonl`. Exposes `POST /ask`, `POST /approve/{action_id}`, `GET /audit`.
4. **ui** (Streamlit) — chat box → shows diagnosis + recommended action → Approve/Deny button → calls the backend. Pure HTTP client, owns no logic of its own.

Nothing beyond these four. No auth, no multi-cluster, no K8s, no DB beyond the one log file. Full task breakdown with owners: [docs/CHECKLIST.md](docs/CHECKLIST.md). Deep-dive architecture with diagrams: [docs/architecture.md](docs/architecture.md).

## Tech stack (final)

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI + Uvicorn |
| LLM | Claude (Anthropic API), via a small custom tool-use agent loop in `backend/app.py` |
| Container control | `docker` Python SDK (docker-py) |
| Frontend | Streamlit |
| Demo app | Python + FastAPI |
| Metrics | Prometheus + cAdvisor |
| Audit store | `audit-log.jsonl` (flat file, volume-mounted) |
| Orchestration | Docker Compose |
| Python package installs | `uv` (never bare `pip`) |

One language (Python) end-to-end — less context-switching for a small team in 6 hours.

## Architecture

```
target-app (FastAPI: /crash /leak /slow, /metrics) ──┐
cadvisor ──> prometheus <────────────────────────────┤
                                                       │
backend (FastAPI, plain python:3.11-slim)
  │  Claude tool-use loop: query_prometheus, get_container_status/logs (read-only),
  │    propose_restart (records a recommendation only)
  │  docker-py: restart <container>  (only on POST /approve)
  │  appends every step ──> audit-log.jsonl
  ▲
  │  POST /ask, POST /approve/{action_id}, GET /audit
ui (Streamlit) ── chat + Approve/Deny button
```

- **One backend container, not two.** The agent's reasoning and the restart action live in the same FastAPI service — the agent stays read-only internally (its tools can only query Prometheus/Docker, never mutate), the restart is our own code path, gated behind `POST /approve` which only fires when a human clicks Approve in the UI. This is the whole "propose → approve → execute → audit" loop, and it's the only piece of custom logic in the project.
- **Why a hand-written tool-use agent, not a wrapped third-party agent framework:** calling the Anthropic Messages API directly with a handful of tool schemas is a small, fully-owned, easily-debugged loop (~150 lines) — no unfamiliar CLI flags or config schema to reverse-engineer under a 6-hour clock. See [docs/holmes-gpt-reference.md](docs/holmes-gpt-reference.md) for the framework this replaced and why.
- **Always `uv`, never bare `pip`.** Every Python install — in every Dockerfile (`target-app`, `backend`, `ui`) and on any laptop setup — goes through `uv` (`uv pip install ...`, or `uv sync` if a service has a `pyproject.toml`). It's a single static binary, resolves and installs faster than pip (matters when you're rebuilding containers repeatedly over 6 hours), and keeps install behavior identical across all three services.
- **Why Claude API, not a local model:** Docker Model Runner is Apple-Silicon-tuned; on Intel it's CPU-only and demo-flaky. Use `ANTHROPIC_API_KEY`.
- **Why Compose, not Kubernetes:** minikube/kind startup alone risks 15–30 min on Intel Mac. Not worth it for 2–3 services in 6 hours.

## Run it

```
docker compose up --build
# target-app   :8080
# prometheus   :9090
# cadvisor     :8081
# backend      :8000
# ui           :8501
```

Env needed: `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`.

## Demo script (for judges)

1. Hit `/leak` on the target app → memory climbs.
2. Ask the copilot: "why is target-app unhealthy?"
3. It correlates Prometheus memory graph + container logs, names the cause, proposes a restart.
4. Click **Approve** → container restarts → confirm health recovers.
5. Show `audit-log.jsonl` — every step logged.

Verified end-to-end (see [docs/CHECKLIST.md](docs/CHECKLIST.md)) — this script runs as described. `/crash` and `/slow` work the same way and are good backup demo beats if `/leak` alone feels thin; `/slow` is a good one to show the agent *not* over-recommending a restart when the issue is self-resolving.

See [docs/CHECKLIST.md](docs/CHECKLIST.md) for the task breakdown and who's building what, and [docs/architecture.md](docs/architecture.md) for the full system + sequence diagrams.
