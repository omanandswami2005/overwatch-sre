# Overwatch-SRE

**What it is:** an LLM copilot that watches a small Dockerized app, answers questions about its health, diagnoses failures, and restarts a broken container — only after a human approves. One chat window instead of four dashboards. Built for a 6.5-hour hackathon.

**Ground rules satisfied:** Docker (Compose + extended `robustadev/holmes` image) + CNCF (Prometheus, graduated — and HolmesGPT itself, CNCF Sandbox).

## What to build (4 pieces, nothing else)

1. **target-app** (FastAPI) — `/crash`, `/leak`, `/slow`, `/metrics`. The thing that breaks on demand.
2. **prometheus + cadvisor** — off-the-shelf compose services, config only, no code.
3. **backend** (FastAPI, image `FROM` extended `robustadev/holmes`) — one container that: calls `holmes ask` (read-only: Docker + Prometheus toolsets) for diagnosis, runs `docker restart <container>` via docker-py *only* when told to, and appends every step to `audit-log.jsonl`. Exposes `POST /ask`, `POST /approve/{action_id}`, `GET /audit`.
4. **ui** (Streamlit) — chat box → shows diagnosis + recommended action → Approve/Deny button → calls the backend. Pure HTTP client, owns no logic of its own.

Nothing beyond these four. No auth, no multi-cluster, no K8s, no DB beyond the one log file. Full task breakdown with owners: [CHECKLIST.md](CHECKLIST.md).

## Tech stack (final)

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI + Uvicorn |
| LLM | Claude (Anthropic API), via HolmesGPT's native integration |
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
backend (FastAPI, image FROM robustadev/holmes+docker-cli)
  │  subprocess: holmes ask  (read-only: docker + prometheus toolsets, Claude via API)
  │  docker-py: restart <container>  (only on POST /approve)
  │  appends every step ──> audit-log.jsonl
  ▲
  │  POST /ask, POST /approve/{action_id}, GET /audit
ui (Streamlit) ── chat + Approve/Deny button
```

- **One backend container, not two.** Holmes reasoning and the restart action live in the same FastAPI service — Holmes stays read-only internally (Docker + Prometheus toolsets only), the restart is our own code path, gated behind `POST /approve` which only fires when a human clicks Approve in the UI. This is the whole "propose → approve → execute → audit" loop, and it's the only piece of custom logic in the project.
- **Why the extended image, not a source build:** `robustadev/holmes` is missing the `docker` CLI binary → `FROM robustadev/holmes:0.36.0` + `RUN apk add --no-cache docker-cli` + `uv pip install fastapi uvicorn`. Building from source via Poetry risks 15–30 min on an Intel Mac for no benefit.
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

Env needed: `ANTHROPIC_API_KEY` in `.env`.

## Demo script (for judges)

1. Hit `/leak` on the target app → memory climbs.
2. Ask the copilot: "why is checkout-service unhealthy?"
3. It correlates Prometheus memory graph + container logs, names the cause, proposes a restart.
4. Click **Approve** → container restarts → confirm health recovers.
5. Show `audit-log.jsonl` — every step logged.

See [CHECKLIST.md](CHECKLIST.md) for the task breakdown and who's building what.
