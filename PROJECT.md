# Overwatch - Your SRE Copilot

Single consolidated reference for the whole project: what it is, what it can do, how the pieces
fit together, what's verified, and what's left. Generated from the current state of the repo
(code, `docker-compose.yml`, and `docs/`) as of 2026-07-25. This file is a snapshot for
orientation — for living, actively-maintained detail see the docs it draws from:
[README.md](README.md), [CLAUDE.md](CLAUDE.md), [docs/architecture.md](docs/architecture.md),
[docs/PROGRESS.md](docs/PROGRESS.md), [docs/CHECKLIST.md](docs/CHECKLIST.md),
[docs/UI-DESIGN.md](docs/UI-DESIGN.md), [docs/SRS-PRD.md](docs/SRS-PRD.md).

## 1. What this is

An LLM copilot — a small, hand-written Claude tool-use agent, not a wrapped third-party
framework — that watches a small set of Dockerized services, answers plain-English questions
about their health, diagnoses failures, and restarts (or rolls back) a broken container — only
after a human clicks **Approve**. It also notices problems on its own: a background watcher runs
cheap deterministic checks and kicks off a real investigation before anyone asks. One chat window
(in a web console or in Slack) instead of four dashboards.

Built for a hackathon. Ground rules satisfied: **Docker** (Compose) + **CNCF** (Prometheus, a
graduated CNCF project).

**Scope discipline:** the original core is `target-app`, `prometheus`+`cadvisor`, `backend`,
`ui`. Everything else — `jaeger`, `grafana`, the librarian/wiki, the report pipeline, the
runbook, the Slack bot, the second watched service — was added deliberately to close real gaps in
the original problem statement (metrics *and* logs *and* traces; a dashboard for judges; more
than one interface), not scope creep. No auth beyond Slack's own, no multi-cluster, no
Kubernetes, no real database — state lives in one JSONL audit log plus generated
Markdown/PDF files.

## 2. How it's put together, in plain English

There's a small **demo app** (`target-app`) and a second, differently-broken **demo app**
(`worker-service`) that the copilot watches. `target-app` can be told to leak memory, crash, or
go slow; `worker-service` can be told to get its queue stuck — two genuinely different failure
shapes, not two copies of the same bug, so the copilot has to actually diagnose rather than
pattern-match on one symptom.

Both apps expose Prometheus metrics (scraped by **Prometheus**, visualized via **cAdvisor** for
container-level CPU/memory) and emit OpenTelemetry traces to **Jaeger**, so there's a real
metrics/logs/traces trio to investigate, not just one signal. **Grafana** sits on top of
Prometheus and Jaeger with a real dashboard, so there's something to point a judge (or an
on-call engineer) at besides a raw log file.

All of that feeds into the **backend**, a FastAPI service that runs the actual copilot. When you
ask it a question, it calls Claude with a set of read-only tools — query Prometheus, read
container logs/status, query traces, search the incident wiki, check the runbook, check incident
history — and, if warranted, it *recommends* an action (restart, or rollback if a restart already
failed once). It never takes that action itself. The recommendation sits pending until a human
approves it in the UI or in Slack; only then does the backend actually call Docker to restart the
container. Every step — the question, the diagnosis, the recommendation, the approval, the
result — gets appended to an audit log, so there's a full paper trail for every incident.

After an approved fix, a second, separate agent (the **librarian**) writes up what happened into
a small self-updating wiki — so next time the same symptom shows up, the copilot can say "this
happened before, here's what fixed it" instead of re-diagnosing from scratch. The copilot also
checks a human-written **runbook** and keeps track of recurrence, so a problem that keeps coming
back gets flagged as recurring and escalated rather than treated as new every time.

None of this requires you to ask first. A background **watcher** thread polls cheap metrics every
30 seconds; if something crosses a threshold, it runs the exact same investigation a typed
question would, on its own, and the resulting proposal shows up in the UI automatically — no
manual "check on it" step needed.

You can talk to the copilot from two places: the **web console** (a Streamlit app with a chat box,
live vitals per service, an audit trail viewer, and a report generator) or **Slack** (a `/overwatch`
slash command or an `@mention`, running as its own container so a flaky Slack connection can never
take down the actual backend). Both talk to the same backend API, so there's one source of truth
either way.

Finally, on demand, the backend can generate a full **incident postmortem report** — a cheap model
compresses the raw history into a brief, a stronger model writes it up as a proper 7-section
Markdown document, downloadable as Markdown or PDF.

## 3. Feature list

These are the same features called out on the app's own landing page — each one is tied to a
real file in the repo, not marketing copy.

- **Self-updating incident wiki.** A second, isolated agent (`backend/librarian.py`) documents
  every resolved incident automatically. The chat agent later cites those write-ups by ID when
  the same symptom recurs, instead of starting from zero.
- **Incident memory + recurrence escalation.** The agent checks past incident history before
  proposing anything (`backend/app.py`). A problem that's happened before gets explicitly flagged
  as recurring and escalated, rather than being investigated as if it were new every time.
- **Codified runbook.** A human-authored, read-only reference (`backend/runbook.md`) of what to
  do for each known failure type, which the agent consults before deciding what to propose —
  separate from the wiki, which records what *actually* happened.
- **Rollback detection.** If a restart was already tried recently and didn't fix the problem
  (`backend/toolsets/remediation_toolset.py`), the copilot recognizes the crash loop and proposes
  a rollback instead of blindly repeating the same restart.
- **Proactive watcher.** A background thread runs cheap checks every 30 seconds with no LLM call
  involved — only when a check actually trips does it invoke the full agent investigation, so the
  copilot can notice and flag a problem before anyone asks.
- **Tracing and dashboards.** Real OpenTelemetry traces flow into Jaeger, and a real Grafana
  dashboard shows container metrics plus an annotation marking exactly when each incident was
  resolved — not just raw numbers in a metrics endpoint.
- **Slack as a second interface.** A separate `slack-bot` container offers `/overwatch <question>`
  and `@mention` support over Slack's Socket Mode, backed by the same approve/restart flow as the
  web UI, plus outbound notifications when something is proposed or resolved.
- **On-demand incident reports.** A cheap model compresses the raw audit history and metrics into
  a brief, a stronger model writes a full 7-section postmortem from it, downloadable as Markdown
  or PDF — generated on request, not baked in advance.
- **Multi-service monitoring.** The copilot watches two services with genuinely different failure
  signatures — a memory leak in `target-app` and a stuck message queue in `worker-service` — so
  its diagnostic range is actually demonstrated, not just its ability to watch one app twice.

## 4. Repo layout

| Path | Owns |
|---|---|
| `target-app/app.py` | Demo app #1 (FastAPI): `/crash`, `/leak`, `/slow`, `/reset`, `/metrics`, OTel-instrumented |
| `worker-service/app.py` | Demo app #2 (FastAPI): stuck-queue failure mode (`/jam`, `/work`, `/reset`), OTel-instrumented |
| `prometheus/prometheus.yml` | Scrape config for both demo apps + cadvisor |
| `backend/app.py` | The copilot itself: chat agent loop, docker-py restart, JSONL audit log, `/incidents` |
| `backend/toolsets/` | Protocol-driven toolset modules (Prometheus, Docker, Jaeger, wiki, runbook, remediation) |
| `backend/toolsets.yaml` | Enable/disable toolsets by key, no code change needed |
| `backend/librarian.py` | Isolated archivist agent — only tool is `write_wiki_pages`, triggered post-approve |
| `backend/runbook.md` | Human-authored steps per failure type, read-only reference for the agent |
| `backend/notifications.py` | `notify_slack()` + `annotate_grafana()` — both best-effort, no-op if unconfigured |
| `backend/watcher.py` | Background thread — proactive per-service checks, triggers the agent on trip |
| `backend/reports.py` | Cheap-model-extract → strong-model-synthesize incident postmortem pipeline + PDF |
| `slack-bot/app.py` | Slack second interface — slash command + mentions, Socket Mode, its own container |
| `grafana/provisioning/`, `grafana/dashboards/overwatch.json` | Provisioned datasources, one real dashboard |
| `scripts/demo-trigger.sh` | One-command demo reset/trigger (`leak`/`crash`/`slow`/`jam`/`reset`) |
| `scripts/run-all.sh` | One command to build, start, health-check the whole stack, and print URLs |
| `ui/app.py` | Multi-page router — landing (`/`), console (`/main`), architecture briefing (`/docs`) |
| `ui/api.py` | The only module in `ui/` that talks to the network — thin HTTP client against the backend |
| `ui/theme.py`, `ui/components/`, `ui/views/` | Modular Streamlit UI: reusable components + per-route views |
| `docker-compose.yml` | Orchestrates every container (Slack bot is opt-in via a Compose profile) |
| `.env.example` | Template for `.env` (gitignored) |

## 5. Tech stack

| Layer | Choice |
|---|---|
| Demo apps / backend | Python 3.11, FastAPI + Uvicorn |
| LLM | Claude (Anthropic API) — a stronger model for the main agent, librarian, and report writing; a cheaper/faster model for report extraction |
| Container control | `docker` Python SDK (docker-py) |
| Web frontend | Streamlit (multi-page) |
| Chat frontend | Slack (Socket Mode, `slack-bolt`) |
| Metrics | Prometheus + cAdvisor |
| Tracing | OpenTelemetry → Jaeger |
| Dashboards | Grafana |
| Audit store | Flat JSONL file on a shared Docker volume |
| Wiki / reports store | Markdown files + generated PDFs, same shared volume |
| PDF rendering | WeasyPrint |
| Orchestration | Docker Compose |
| Python package installs | `uv`, never bare `pip` |

## 6. API contract (backend ↔ ui / slack-bot)

- `POST /ask {question}` → `{answer, recommended_action, action_id}` — `recommended_action` is
  `null` unless the agent recommended a restart or rollback. Every ask is tagged with a `source`:
  a person typing in the UI, Slack, or the watcher triggering itself.
- `POST /approve/{action_id}` → `{status, container, result?}` — the *only* place a mutating
  action executes. On success, best-effort triggers the librarian, a Slack notification, and a
  Grafana annotation.
- `GET /audit` → the full JSONL event log. `GET /incidents` → those events grouped into
  ask/approve pairs, with a flag for which are still actionable.
- `POST /report/generate {context, container?}` → kicks off the two-stage postmortem pipeline.
  `GET /reports`, `GET /report/{id}/md`, `GET /report/{id}/pdf` → list/fetch generated reports.
- `POST /demo/trigger/{service}/{mode}` → proxies to a demo app's own failure-injection endpoint,
  for one-command demo scenarios without the UI needing to know the demo apps exist directly.
- `GET /healthz` → liveness check.

## 7. Services and ports (`docker compose up --build`)

| Service | Port | Notes |
|---|---|---|
| `target-app` | 8080 | Demo app #1 |
| `worker-service` | 8090 | Demo app #2 |
| `prometheus` | 9090 | Scrapes both demo apps + cadvisor |
| `cadvisor` | 8081 | Container-level metrics source |
| `jaeger` | 16686 (UI/API), 4317 (OTLP gRPC) | Traces |
| `grafana` | 3000 | admin/admin, or anonymous Viewer |
| `backend` | 8000 | The copilot's API |
| `ui` | 8501 | Streamlit console |
| `slack-bot` | — (no exposed port) | Opt-in: `docker compose --profile slack up`, needs real Slack tokens |

`scripts/run-all.sh` builds, starts, health-checks every service via its own endpoint, and prints
all URLs.

## 8. Dev loop

`backend` bind-mounts `./backend:/app` and runs with `--reload` — editing backend code takes
effect immediately, no rebuild needed. Only rebuild when `requirements.txt` or a `Dockerfile`
changes. The two demo apps have no bind mount, so they need an explicit rebuild to pick up code
changes.

All Dockerfiles use BuildKit cache mounts for `uv`/apt so repeated rebuilds stay fast, plus a
`.dockerignore` per service.

## 9. Real bugs found and fixed along the way

- **Empty-answer bug**: the agent's token budget was too small and the model's internal
  "thinking" could consume the whole budget across multi-round tool calls before writing any
  answer text, silently returning an empty response. Fixed by raising the budget and explicitly
  handling the truncated case.
- **Stale status pill**: the console derived a service's status from only the most recent audit
  event, but events from the librarian/report pipeline land *after* the actual approve/restart —
  so a freshly-recovered service could misread as "healthy" instead of "recovering." Fixed to
  scan backward for the most recent relevant event.
- **Watcher metric mislabeling**: the original leak check queried one hardcoded metric name with
  no per-service scoping — harmless with one watched service, but would have silently mislabeled
  the second one (which doesn't emit that metric at all) once it was added. Fixed with an
  explicit per-service metric+threshold table.
- **Cross-service status bleed**: the same status-pill logic didn't filter by which container an
  event was actually about, so an action on one service could flip the other service's status
  dot. Fixed to filter by container.
- **Silent proposals**: watcher- or Slack-triggered proposals never showed up as actionable cards
  in the console unless the user happened to ask something themselves first. Fixed by having the
  console pull pending incidents from the backend and auto-refresh, instead of relying purely on
  client-side chat state.
- **Stuck pending cards**: a backend restart clears its in-memory record of pending actions, but
  the audit log alone couldn't tell old proposals from genuinely-pending ones — old proposals
  would show as "pending" forever. Fixed by tracking which proposals are actually still
  approvable.

## 10. Verified vs. proposed

Every feature described above (core diagnose/propose/approve/restart loop across both demo apps,
the toolset framework, the librarian + wiki, the runbook, recurrence escalation, rollback
detection, Slack notifications + Grafana annotations, the proactive watcher, Jaeger tracing, the
Grafana dashboard, the Slack bot's Socket Mode connection, the incident report pipeline including
its UI panel, and the multi-service watch) has been exercised end-to-end against a real running
stack — real `docker compose` runs, real API calls, no simulated results. One piece is explicitly
**not yet human-confirmed**: an actual `/overwatch` or `@mention` round-trip typed live inside the
real Slack workspace — the bot's connection to Slack itself is verified, but the last step (typing
the command as a person in Slack) needs a human in that workspace to try it. Full verification
detail (exact commands, exact outputs) lives in [docs/PROGRESS.md](docs/PROGRESS.md); check there
before relying on any specific claim, since it's updated more often than this file.

**Proposed, discussed, not started:**
- **Centralized/searchable logs** (e.g. Loki) — current raw-container-log access satisfies
  diagnosis needs but there's no aggregated, dashboarded log store the way Grafana/Jaeger give
  for metrics/traces. Not committed to.
- **GitHub PR from incident writeups** — deferred pending a token with repo write scope; the wiki
  is already plain Markdown specifically so this is a fast follow later.
- **Docker MCP Gateway + GitHub MCP server** — researched as the "proper" way to ship the GitHub
  PR feature using a real Docker product instead of hand-rolled API calls. Not started.

## 11. No automated tests yet

No automated test suite exists in any service as of this writing — verification so far has been
live, manual runs against the real stack plus direct API calls, documented in `docs/PROGRESS.md`.

## 12. Environment setup

```
cp .env.example .env   # fill in ANTHROPIC_API_KEY; everything else is optional
docker compose up --build
# add the Slack bot too: docker compose --profile slack up --build
# or: scripts/run-all.sh   (build + start + health-check + print URLs)
```

Required: `ANTHROPIC_API_KEY`. Optional: model overrides, `SLACK_WEBHOOK_URL` (notifications),
`SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` (the Slack bot interface), and the watcher's tuning
knobs — see `.env.example` for the full list and defaults.

## 13. Demo script (for judges)

1. Trigger a failure on either demo app (a leak/crash/slow on `target-app`, or a jam on
   `worker-service`) via the one-command script, or just wait for the watcher to catch it on its
   own.
2. Ask the copilot what's wrong, or watch it flag the problem unprompted.
3. It correlates metrics, logs, and traces, names the cause, and proposes a fix — a restart, or a
   rollback if a restart already failed once.
4. Click **Approve** (in the web console or in Slack) → the container restarts → confirm recovery.
5. Show the audit trail — every step logged — and the Grafana dashboard picking up the incident
   annotation.
6. Optional: generate a full incident postmortem report and pull the PDF.
