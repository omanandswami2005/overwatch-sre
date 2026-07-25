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
  │  Claude tool-use loop (_run_agent in app.py) driven by a toolset registry:
  │    toolsets/prometheus_toolset.py  → query_prometheus        (read-only)
  │    toolsets/docker_toolset.py      → get_container_status/logs (read-only)
  │    toolsets/remediation_toolset.py → propose_restart          (recommend only)
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

**Toolset framework** (`backend/toolsets/`) — a small protocol-driven plugin system, our own
replacement for what HolmesGPT's toolset config used to provide (see
[docs/holmes-gpt-reference.md](docs/holmes-gpt-reference.md)):
- `base.py` defines `Toolset` as a `typing.Protocol` — `name`, `read_only`, `schemas()`,
  `call(tool_name, tool_input)`. Any class matching that shape qualifies; no inheritance
  required.
- `registry.py`'s `ToolsetRegistry` aggregates enabled toolsets into one Claude `tools=` list
  and dispatches `tool_use` blocks to whichever toolset owns that tool name.
- `backend/toolsets.yaml` enables/disables toolsets by key (`prometheus`, `docker`,
  `remediation`) without touching code.
- **To add a capability:** write a module matching `Toolset` in `backend/toolsets/`, register
  its factory in `app.py`'s `_build_registry()`, add it to `toolsets.yaml`. The agent loop
  (`_run_agent`) never changes.

## Repo layout

| Path | Owns | Lane (CHECKLIST.md) |
|---|---|---|
| `target-app/app.py` | FastAPI demo app: `/crash`, `/leak`, `/slow`, `/reset`, `/metrics` (Prometheus format) | A |
| `prometheus/prometheus.yml` | Scrape config for target-app + cadvisor | A |
| `backend/app.py` | FastAPI wrapper: generic tool-use loop, docker-py restart, JSONL audit log | B |
| `backend/toolsets/` | Protocol-driven toolset modules (`base.py`, `registry.py`, `*_toolset.py`) | B |
| `backend/toolsets.yaml` | Enable/disable toolsets by key, no code change needed | B |
| `backend/Dockerfile` | plain `python:3.11-slim` + fastapi/uvicorn/anthropic/docker/pyyaml via `uv` | B |
| `ui/app.py` | Streamlit chat UI, pure HTTP client against the backend, no logic of its own | C |
| `ui/.streamlit/config.toml` | Dark theme tokens matching UI-DESIGN.md | C |
| `docker-compose.yml` | Orchestrates all 5 containers; backend gets Docker socket + `audit-log` volume | A/B |
| `.env.example` | Template for `.env` (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) — `.env` itself is gitignored | — |

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
  the `anthropic` Python SDK in `backend/app.py`. Copy `.env.example` to `.env` and fill in the
  key; `.env` is gitignored, so share keys with teammates out-of-band, never via git. Model id
  is configurable via `ANTHROPIC_MODEL` (defaults to `claude-sonnet-5`).
- **Update docs alongside code, not after.** When a change affects architecture, the API
  contract, or repo layout, update `CLAUDE.md`/`docs/architecture.md`/`docs/CHECKLIST.md` in the
  same batch of edits — don't defer doc updates to a separate pass at the end.
- Commit style per `docs/CHECKLIST.md`: claim a task with a one-line commit (`chore: claim
  A-1`) before starting; commit directly to `main` unless mid-breakage.
- Design tokens (colors, type, copy voice) for the UI are canonical in
  [docs/UI-DESIGN.md](docs/UI-DESIGN.md) — check there before changing anything visual in
  `ui/app.py` or `ui/.streamlit/config.toml`.

## Known gaps / unverified as of last read

- No tests exist yet in any of the four services.
- This project previously wrapped HolmesGPT (an external CLI/agent) instead of calling Claude
  directly; that approach was replaced with the custom tool-use agent described above. See
  [docs/holmes-gpt-reference.md](docs/holmes-gpt-reference.md) for why, kept only as a
  removable historical record — nothing in the active codebase depends on it.

## Running it — and iterating on the backend without rebuilding

`docker-compose.yml` exists and has been verified end-to-end for all three failure modes
(`/leak`, `/slow`, `/crash`): correct diagnosis in each case, `propose_restart` → `/approve` →
container actually restarts and recovers where a restart was warranted, `/slow` correctly gets
no restart proposal since it's self-resolving, and every event lands in the audit trail.

`backend` bind-mounts `./backend:/app` and runs `uvicorn --reload` — editing `app.py` or
anything in `toolsets/` takes effect immediately in the running container, no
`docker compose up --build` needed. Only rebuild (`docker compose up --build backend`) when
`requirements.txt` or the `Dockerfile` itself changes. For quick one-off checks against the live
container without even waiting on a reload, `docker compose exec backend python3 -c "..."` can
exercise `toolsets`/`anthropic` directly (see how the `max_tokens` truncation bug below was
found and reproduced).

**Fixed:** `_run_agent()` originally called the Messages API with `max_tokens=1024`. This model
emits "thinking" content blocks by default, which can consume the entire token budget across
multi-round tool calls before any answer text is generated — `stop_reason` comes back as
something other than `"tool_use"` with zero `"text"` blocks, silently producing an empty
`answer`. Fixed by raising `max_tokens` to 4096 and explicitly handling `stop_reason ==
"max_tokens"` and empty-text cases with a real fallback message instead of returning `""`.

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY
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
