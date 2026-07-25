# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

Overwatch-SRE: an LLM copilot (HolmesGPT + Claude) that watches a small Dockerized app,
answers questions about its health, diagnoses failures, and restarts a broken container —
only after a human clicks Approve. Built for a 6.5-hour hackathon. One chat window instead
of four dashboards.

Full narrative/architecture: [README.md](README.md). Task breakdown and lane ownership:
[CHECKLIST.md](CHECKLIST.md). UI visual spec: [UI-DESIGN.md](UI-DESIGN.md). Read those for
depth — this file is the orientation layer, not a replacement.

**Scope discipline:** exactly four pieces (`target-app`, `prometheus`+`cadvisor`, `backend`,
`ui`). No auth, no multi-cluster, no Kubernetes, no database beyond one JSONL log file. Don't
add scope beyond what CHECKLIST.md lists — this is a time-boxed hackathon build, not a product.

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

**The one piece of custom logic in this project** is the propose → approve → execute → audit
loop in `backend/app.py`. Holmes itself stays strictly read-only (docker + prometheus
toolsets only, see `backend/holmes-config.yaml`); the container restart is our own code path,
gated behind `POST /approve/{action_id}`, which only fires when a human clicks Approve in the
UI. Never give Holmes a write/mutating toolset — that would collapse the human-in-the-loop
gate the whole design rests on.

## Repo layout

| Path | Owns | Lane (CHECKLIST.md) |
|---|---|---|
| `target-app/app.py` | FastAPI demo app: `/crash`, `/leak`, `/slow`, `/reset`, `/metrics` (Prometheus format) | A |
| `prometheus/prometheus.yml` | Scrape config for target-app + cadvisor | A |
| `backend/app.py` | FastAPI wrapper: shells out to `holmes ask`, docker-py restart, JSONL audit log | B |
| `backend/holmes-config.yaml` | Holmes toolset config — keeps Holmes read-only | B |
| `backend/Dockerfile` | `FROM robustadev/holmes:0.36.0` + docker-cli + fastapi/uvicorn via `uv` | B |
| `ui/app.py` | Streamlit chat UI, pure HTTP client against the backend, no logic of its own | C |
| `ui/.streamlit/config.toml` | Dark theme tokens matching UI-DESIGN.md | C |

Lanes work in parallel and should stay out of each other's files (per CHECKLIST.md). If you're
picking up a task, check whether it's claimed (owner line in CHECKLIST.md) before starting.

## API contract (backend ↔ ui)

- `POST /ask {question}` → `{answer, recommended_action, action_id}` — `recommended_action` is
  `null` unless the diagnosis warrants one (currently a keyword-trigger regex in `app.py`,
  `RESTART_TRIGGERS` — a hackathon-grade heuristic, swap for a structured Holmes response if
  time allows).
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
- **Claude via Anthropic API** (`ANTHROPIC_API_KEY`), not a local model — Holmes calls it
  natively. Requires `.env` with that key (not yet added to the repo — see Known gaps).
- Commit style per CHECKLIST.md: claim a task with a one-line commit (`chore: claim A-1`)
  before starting; commit directly to `main` unless mid-breakage.
- Design tokens (colors, type, copy voice) for the UI are canonical in
  [UI-DESIGN.md](UI-DESIGN.md) — check there before changing anything visual in `ui/app.py` or
  `ui/.streamlit/config.toml`.

## Known gaps / unverified as of last read

- **No `docker-compose.yml` yet** (CHECKLIST.md task A-2, unclaimed) — needed to actually run
  `docker compose up --build` as documented in README.md.
- **No `.env` / `.env.example`** — `ANTHROPIC_API_KEY` isn't scaffolded anywhere yet.
- `backend/app.py`'s `_ask_holmes()` invokes `python /app/holmes_cli.py ask <question>` —
  flagged in-code as unverified against the actual installed Holmes CLI's `--help` output.
  Confirm before relying on it.
- `backend/holmes-config.yaml` keys are flagged in-code as unverified against the installed
  Holmes version's config schema.
- No tests exist yet in any of the four services.

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
