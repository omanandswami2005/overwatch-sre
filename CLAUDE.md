# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

Overwatch-SRE: an LLM copilot (a small custom Claude tool-use agent) that watches a small
Dockerized app, answers questions about its health, diagnoses failures, and restarts a broken
container — only after a human clicks Approve. Built for a 6.5-hour hackathon. One chat window
instead of four dashboards.

Full narrative/architecture: [README.md](README.md). Deep-dive system + sequence diagrams:
[docs/architecture.md](docs/architecture.md). Task breakdown and lane ownership:
[docs/CHECKLIST.md](docs/CHECKLIST.md). UI visual spec: [docs/UI-DESIGN.md](docs/UI-DESIGN.md).
Read those for depth — this file is the orientation layer, not a replacement.

**Scope discipline:** exactly four pieces (`target-app`, `prometheus`+`cadvisor`, `backend`,
`ui`). No auth, no multi-cluster, no Kubernetes, no database beyond one JSONL log file. Don't
add scope beyond what CHECKLIST.md lists — this is a time-boxed hackathon build, not a product.

## Architecture

```
target-app (FastAPI: /crash /leak /slow, /metrics) ──┐
cadvisor ──> prometheus <────────────────────────────┤
                                                       │
backend (FastAPI, plain python:3.11-slim)
  │  Claude tool-use loop (_run_agent in app.py): query_prometheus,
  │    get_container_status/logs (read-only), propose_restart (recommend only)
  │  docker-py: restart <container>  (only on POST /approve)
  │  appends every step ──> audit-log.jsonl
  ▲
  │  POST /ask, POST /approve/{action_id}, GET /audit
ui (Streamlit) ── chat + Approve/Deny button
```

**The one piece of custom logic in this project** is the propose → approve → execute → audit
loop in `backend/app.py`. The agent itself only ever gets read-only tools (query Prometheus,
read container status/logs) plus `propose_restart`, which *records* a recommendation and never
touches the Docker daemon; the container restart is a separate code path,
gated behind `POST /approve/{action_id}`, which only fires when a human clicks Approve in the
UI. Never give the agent a tool that mutates state directly — that would collapse the
human-in-the-loop gate the whole design rests on.

## Repo layout

| Path | Owns | Lane (CHECKLIST.md) |
|---|---|---|
| `target-app/app.py` | FastAPI demo app: `/crash`, `/leak`, `/slow`, `/reset`, `/metrics` (Prometheus format) | A |
| `prometheus/prometheus.yml` | Scrape config for target-app + cadvisor | A |
| `backend/app.py` | FastAPI wrapper: Claude tool-use agent loop, docker-py restart, JSONL audit log | B |
| `backend/Dockerfile` | plain `python:3.11-slim` + fastapi/uvicorn/anthropic/docker via `uv` | B |
| `ui/app.py` | Streamlit chat UI, pure HTTP client against the backend, no logic of its own | C |
| `ui/.streamlit/config.toml` | Dark theme tokens matching UI-DESIGN.md | C |

Lanes work in parallel and should stay out of each other's files (per `docs/CHECKLIST.md`). If
you're picking up a task, check whether it's claimed (owner line in `docs/CHECKLIST.md`) before
starting.

## API contract (backend ↔ ui)

- `POST /ask {question}` → `{answer, recommended_action, action_id}` — `recommended_action` is
  `null` unless the agent called its `propose_restart` tool during the tool-use loop in
  `_run_agent()` (`backend/app.py`).
- `POST /approve/{action_id}` → `{status, container, result?}` — runs `docker restart` via
  docker-py. This is the *only* place a mutating action executes.
- `GET /audit` → list of JSONL-logged events (`ask`, `ask_error`, `approve`), each with a `ts`.
- `GET /healthz` → liveness check.

UI renders strictly against this shape — see `ui/app.py`'s `fetch_audit()` / chat flow. Don't
change the contract without updating both sides.

## Conventions

- **`uv`, never bare `pip`.** Every Dockerfile (`target-app`, `backend`, `ui`) installs via
  `uv pip install --system --no-cache -r requirements.txt`, copying the static `uv` binary from
  `ghcr.io/astral-sh/uv:latest`. Keep new installs consistent with this.
- **Python 3.11, FastAPI + Uvicorn** end-to-end for `target-app`/`backend`; Streamlit for `ui`.
  One language on purpose — less context-switching in a 6-hour build.
- **Claude via Anthropic API** (`ANTHROPIC_API_KEY`), not a local model — called directly via
  the `anthropic` Python SDK in `backend/app.py`. Requires `.env` with that key (not yet added
  to the repo — see Known gaps). Model id is configurable via `ANTHROPIC_MODEL` (defaults to
  `claude-sonnet-5`).
- Commit style per `docs/CHECKLIST.md`: claim a task with a one-line commit (`chore: claim
  A-1`) before starting; commit directly to `main` unless mid-breakage.
- Design tokens (colors, type, copy voice) for the UI are canonical in
  [docs/UI-DESIGN.md](docs/UI-DESIGN.md) — check there before changing anything visual in
  `ui/app.py` or `ui/.streamlit/config.toml`.

## Known gaps / unverified as of last read

- **No `docker-compose.yml` yet** (`docs/CHECKLIST.md` task A-2, unclaimed) — needed to actually run
  `docker compose up --build` as documented in README.md.
- **No `.env` / `.env.example`** — `ANTHROPIC_API_KEY` isn't scaffolded anywhere yet.
- No tests exist yet in any of the four services.
- This project previously wrapped HolmesGPT (an external CLI/agent) instead of calling Claude
  directly; that approach was replaced with the custom tool-use agent described above. See
  [docs/holmes-gpt-reference.md](docs/holmes-gpt-reference.md) for why, kept only as a
  removable historical record — nothing in the active codebase depends on it.

## Running it (once docker-compose.yml exists)

```
docker compose up --build
# target-app   :8080
# prometheus   :9090
# cadvisor     :8081
# backend      :8000
# ui           :8501
```

## Git / GitHub identity

This repo pushes as GitHub user `omanandswami2005` (`omanandswami2005@gmail.com`) — both
`gh` active account and local `git config user.*` are set to that identity. Don't switch back
to `omanandswami2005atdax` without being asked.

Commit at each milestone (a completed CHECKLIST.md task or a meaningful batch of edits) and
push to `origin/main` unless told otherwise.
