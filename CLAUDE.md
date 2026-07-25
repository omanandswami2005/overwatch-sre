# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

Overwatch-SRE: an LLM copilot (a small custom Claude tool-use agent) that watches a small
Dockerized app, answers questions about its health, diagnoses failures, and restarts a broken
container — only after a human clicks Approve. It also notices problems on its own: a
background watcher runs cheap deterministic checks and kicks off a real investigation before
anyone asks. Built for a 6.5-hour hackathon. One chat window instead of four dashboards.

Full narrative/architecture: [README.md](README.md). Deep-dive system + sequence diagrams:
[docs/architecture.md](docs/architecture.md). Task breakdown and lane ownership:
[docs/CHECKLIST.md](docs/CHECKLIST.md). UI visual spec: [docs/UI-DESIGN.md](docs/UI-DESIGN.md).
**Live status — what's verified vs. in-progress vs. proposed-not-started:**
[docs/PROGRESS.md](docs/PROGRESS.md), kept current as the fastest way to get oriented mid-build.
Read those for depth — this file is the orientation layer, not a replacement.

**Scope discipline:** core pieces are `target-app`, `prometheus`+`cadvisor`, `backend`, `ui` —
`jaeger` (tracing) and `grafana` (dashboards) were added deliberately later to close a real gap
(the problem statement's "metrics/logs/traces," and "we need a dashboard for judges"), not scope
creep; see `docs/PROGRESS.md` for what's verified vs. proposed. No auth, no multi-cluster, no
Kubernetes, no database beyond one JSONL log file. This is a time-boxed hackathon build, not a
product — check `docs/PROGRESS.md` before adding anything else.

## Architecture

```
target-app (FastAPI: /crash /leak /slow, /metrics) ──┐
cadvisor ──> prometheus <────────────────────────────┤──> grafana (dashboards, :3000)
target-app --OTLP--> jaeger (traces, :16686) <────────┘
                                                       │
backend (FastAPI, plain python:3.11-slim)
  │  Chat agent (_run_agent in app.py), read-only + propose, via toolset registry:
  │    toolsets/prometheus_toolset.py  → query_prometheus          (read-only)
  │    toolsets/docker_toolset.py      → get_container_status/logs (read-only)
  │    toolsets/jaeger_toolset.py      → query_traces               (read-only)
  │    toolsets/wiki_toolset.py        → search_wiki/read_wiki_page (read-only)
  │    toolsets/remediation_toolset.py → propose_restart            (recommend only)
  │  docker-py: restart <container>  (only on POST /approve)
  │  librarian.py: isolated agent, write_wiki_pages ONLY, triggered
  │    automatically (best-effort) after an approved restart succeeds
  │  notifications.py: Slack webhook + Grafana annotation, both on
  │    proposal / approve outcome (annotation only on success)
  │  watcher.py: background thread, cheap checks every 30s, triggers
  │    the SAME _handle_ask() path as a user question when one trips
  │  appends every step ──> audit-log.jsonl
  ▲
  │  POST /ask, POST /approve/{action_id}, GET /audit, GET /incidents
ui (Streamlit) ── chat + Approve/Deny button
```

**The one piece of custom logic in this project** is the propose → approve → execute → audit
loop in `backend/app.py`. The chat agent only ever gets read-only tools (query Prometheus, read
container status/logs, search the wiki) plus `propose_restart`, which *records* a recommendation
and never touches the Docker daemon; the container restart is a separate code path, gated behind
`POST /approve/{action_id}`, which only fires when a human clicks Approve in the UI. Never give
the chat agent a tool that mutates state directly — that would collapse the human-in-the-loop
gate the whole design rests on.

**Librarian agent + wiki** (`backend/librarian.py`) — a second, isolated agent that documents
resolved incidents. After `/approve/{action_id}` successfully restarts a container, the backend
calls `run_librarian()` (best-effort, wrapped in try/except — a librarian failure never affects
the `/approve` response) with the incident's question/diagnosis/action/result. The librarian's
only tool is `write_wiki_pages` — forced via `tool_choice`, one call, writes
`wiki/index.md`, `wiki/services/<container>.md`, `wiki/incidents/<action_id>.md`. This tool is
**not** registered anywhere in `ToolsetRegistry` — the chat agent structurally cannot write to
the wiki, there's no config flag that could leak that capability to it. `WikiToolset`
(read-only: `search_wiki`, `read_wiki_page`) is what the chat agent uses to consult what the
librarian has written — always cross-checked against live data, since the wiki can be stale.
Path safety: `_safe_wiki_path()` refuses to write outside `WIKI_DIR` — the librarian's paths
come from LLM output, so they're untrusted input.

**Slack notifications** (`backend/notifications.py`) — `notify_slack()` posts to
`SLACK_WEBHOOK_URL` (best-effort, no-ops silently if unset — never raises). Fired on: a
`propose_restart` in `/ask`, and the outcome of `/approve`. Deliberately backend-triggered, not
LLM-invoked (same reasoning as the restart gate — notification timing is a deterministic policy,
not something to hand the model discretion over) and not implemented in `ui/` — it fires
automatically off the UI's normal `/ask`/`/approve` calls, no UI code changes needed.

**Slack bot** (`slack-bot/app.py`) — a second first-class interface, not just a notification:
`/overwatch <question>` in Slack, backed by Socket Mode (no public URL/tunnel needed in Compose)
via `slack-bolt`. A separate container from `backend` on purpose — failure isolation, a dropped
Slack WebSocket can't affect the backend or `ui/`. It is a pure HTTP client of the same
`/ask`→`/approve/{action_id}` contract `ui/` uses, nothing more — same reasoning as `ui/` itself
having no logic of its own. Slack requires a 3-second ack on slash commands, so the real
`_run_agent` call (which can take tens of seconds) runs in a background thread; the result is
delivered via `respond()` (Slack's `response_url` under the hood). A `propose_restart` renders as
Approve/Dismiss buttons in Slack itself. Opt-in: only starts with
`docker compose --profile slack up` and needs `SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` from a Slack
App created at api.slack.com with Socket Mode enabled — silently absent otherwise, no impact on
the default `docker compose up` path.

**Proactive watcher** (`backend/watcher.py`) — the part that actually earns the word "copilot":
without it, the whole system is purely reactive (only investigates when asked), which undersells
the product. A daemon thread runs `check_once()` every `WATCH_INTERVAL_SECONDS` (default 30) per
container in `WATCH_CONTAINERS` (default `target-app`) — two cheap, deterministic checks, no LLM
call: `app_leak_bytes >= LEAK_THRESHOLD_BYTES` via Prometheus, and container status via
docker-py. Only when a check trips does it call `_handle_ask(question, source="watcher")` — the
exact same function `/ask` uses, so a proactive investigation gets the identical
diagnosis/propose/audit/Slack/librarian pipeline as a typed question, just a different
`source` tag in the audit log. Each `(container, check)` pair has its own
`WATCH_COOLDOWN_SECONDS` (default 300) so an ongoing, un-remediated issue doesn't re-trigger a
full LLM investigation every 30s. Set `WATCH_ENABLED=false` to disable. Callback-based
(`watcher.start(docker_client, on_trigger=...)`) specifically to avoid `watcher.py` importing
`app.py` — `app.py` imports `watcher`, not the other way around.

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
| `target-app/app.py` | FastAPI demo app: `/crash`, `/leak`, `/slow`, `/reset`, `/metrics` (Prometheus format), OTel-instrumented | A |
| `worker-service/app.py` | Second watched service — different failure signature (`/jam`, stuck-queue, not a leak) | A |
| `prometheus/prometheus.yml` | Scrape config for target-app + cadvisor | A |
| `backend/app.py` | FastAPI wrapper: chat agent loop, docker-py restart, JSONL audit log, `/incidents` | B |
| `backend/toolsets/` | Protocol-driven toolset modules (`base.py`, `registry.py`, `*_toolset.py`, incl. `jaeger_toolset.py`) | B |
| `backend/toolsets.yaml` | Enable/disable toolsets by key, no code change needed | B |
| `backend/librarian.py` | Isolated archivist agent — only tool is `write_wiki_pages`, triggered post-approve | B |
| `backend/notifications.py` | `notify_slack()` + `annotate_grafana()` — both best-effort, no-op if unconfigured | B |
| `backend/watcher.py` | Background thread — proactive checks, triggers `_handle_ask` on trip | B |
| `backend/reports.py` | Haiku-extract → Sonnet-synthesize incident postmortem pipeline + WeasyPrint PDF | B |
| `backend/Dockerfile` | `python:3.11-slim` + apt (WeasyPrint native libs) + fastapi/uvicorn/anthropic/docker/pyyaml/requests/markdown/weasyprint via `uv` | B |
| `grafana/provisioning/`, `grafana/dashboards/overwatch.json` | Provisioned Prometheus+Jaeger datasources, one real dashboard | A |
| `scripts/demo-trigger.sh` | One-command demo reset/trigger (`leak`/`crash`/`slow`/`reset`), no raw `curl` needed | — |
| `ui/app.py` | Multi-page router (`st.navigation`) — landing page (`/`) + console (`/main`) | C |
| `ui/api.py` | The only module in `ui/` that talks to the network — thin HTTP client against the backend | C |
| `ui/theme.py`, `ui/components/`, `ui/views/` | Modular Streamlit UI: reusable components + per-route views (`/`, `/main`, `/docs`) | C |
| `ui/.streamlit/config.toml` | Dark theme tokens matching UI-DESIGN.md | C |
| `slack-bot/app.py` | Second first-class interface: `/overwatch` slash command (Socket Mode), pure HTTP client of the same `/ask`→`/approve/{id}` contract `ui/` uses. Opt-in via `docker compose --profile slack up` | — |
| `docker-compose.yml` | Orchestrates 8 containers (7 by default + `slack-bot` behind the `slack` profile); backend gets Docker socket + `backend-data` volume (audit log + wiki + reports) | A/B |
| `.env.example` | Template for `.env` — `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `HAIKU_MODEL`, `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN`, `WATCH_*` — `.env` itself is gitignored | — |

Lanes work in parallel and should stay out of each other's files (per `docs/CHECKLIST.md`). If
you're picking up a task, check whether it's claimed (owner line in `docs/CHECKLIST.md`) before
starting.

## API contract (backend ↔ ui)

- `POST /ask {question}` → `{answer, recommended_action, action_id}` — `recommended_action` is
  `null` unless the agent called its `propose_restart` tool during the tool-use loop in
  `_run_agent()` (`backend/app.py`). Audited `ask` events also carry `source`: `"user"` for this
  route, `"watcher"` when `backend/watcher.py`'s background thread triggered it proactively —
  the UI's HTTP contract itself is unchanged, this is audit/incident metadata only.
- `POST /approve/{action_id}` → `{status, container, result?}` — runs `docker restart` via
  docker-py. This is the *only* place a mutating action executes. On success, also
  (best-effort) triggers the librarian and a Slack notification.
- `GET /audit` → list of JSONL-logged events (`ask`, `ask_error`, `approve`, `librarian`,
  `librarian_error`), each with a `ts`.
- `GET /incidents` → audit events grouped into `{ask, approve}` pairs by `action_id` — asks
  with no proposed action are omitted (not incidents).
- `POST /report/generate {context, container?}` → `{id, created_at}` — two-stage pipeline
  (`backend/reports.py`): Haiku compresses raw audit-log + Prometheus range data into a brief,
  Sonnet writes a 7-section Markdown postmortem from that brief + `context`. Not an agent tool —
  triggered directly by a human request.
- `GET /reports` → list of generated reports. `GET /report/{id}/md` → raw Markdown.
  `GET /report/{id}/pdf` → rendered PDF (WeasyPrint), `application/pdf`.
- `POST /demo/trigger/{mode}` (`mode` ∈ `leak`/`crash`/`slow`/`reset`) → proxies to
  `target-app`'s own endpoint. Demo convenience only, not part of the real contract above — lets
  a future UI button trigger a scenario without knowing `target-app` exists directly.
- `GET /healthz` → liveness check.

UI renders strictly against this shape — see `ui/api.py` (the only network-facing module) and
`ui/components/chat.py`/`vitals.py`. Don't
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
  `ui/theme.py`, `ui/components/`, or `ui/.streamlit/config.toml`.

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
no restart proposal since it's self-resolving, and every event lands in the audit trail. The
librarian + wiki loop is also verified: after an approved restart, `wiki/index.md`,
`wiki/services/<container>.md`, and `wiki/incidents/<action_id>.md` all get written correctly,
and a follow-up `/ask` about the same symptom correctly cites the prior incident by ID via
`search_wiki` before falling back to live data. The watcher is verified too: pushed `target-app`
over `LEAK_THRESHOLD_BYTES` via `/leak` with zero manual `/ask` calls, and within one
`WATCH_INTERVAL_SECONDS` cycle it investigated on its own, correctly cited the earlier incident
from the wiki, and proposed a restart — `source: "watcher"` in the audit log confirms it, not a
user-typed question.

Tracing and dashboards are verified too, not just wired: `target-app` traces confirmed landing
in Jaeger (`curl localhost:16686/api/services` lists it, real spans with real durations pulled
back), the `query_traces` tool confirmed working through the live agent (asked a latency
question, got real span-duration numbers back, not a hallucinated summary), and the Grafana
dashboard's four panels plus the restart-triggered annotation all confirmed returning real data
through Grafana's own API — see [docs/PROGRESS.md](docs/PROGRESS.md) for the exact verification
steps, including a real cAdvisor label limitation on this host that was found and worked around
rather than papered over.

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
