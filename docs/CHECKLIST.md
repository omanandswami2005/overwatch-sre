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

**Wave 3 — beyond the original scope, added deliberately (see `docs/PROGRESS.md` for why each)**
- [x] E-1 Librarian agent + self-updating wiki (`backend/librarian.py`, `wiki_toolset.py`) —
  verified: wiki pages written after approved restarts, cited correctly on follow-up questions
- [x] E-2 Slack notifications + Grafana incident annotations (`backend/notifications.py`) —
  verified against real endpoints
- [x] E-3 Proactive watcher (`backend/watcher.py`) — verified live, zero manual `/ask` needed
- [x] E-4 OpenTelemetry tracing → Jaeger + `query_traces` tool — verified: real traces, real
  agent tool use
- [x] E-5 Grafana dashboard (4 panels + restart annotations) — verified real data through
  Grafana's own API, including a real cAdvisor label limitation found and worked around
- [x] E-6 Docker build speed: BuildKit cache mounts (uv + apt) across all 3 Dockerfiles,
  `.dockerignore` added — verified with a forced `--no-cache` rebuild staying fast
- [x] E-7 `scripts/demo-trigger.sh` + `POST /demo/trigger/{mode}` backend passthrough — verified
  live, one-command demo reset/trigger without needing raw `curl`
- [x] E-8 Incident report pipeline: Haiku extracts a compressed brief from raw audit-log +
  Prometheus range data, Sonnet synthesizes a 7-section Markdown postmortem, WeasyPrint renders
  PDF on demand (`POST /report/generate`, `GET /report/{id}/md`, `GET /report/{id}/pdf`,
  `GET /reports`) — verified: real report citing real action IDs/timestamps from this session,
  real PDF confirmed via `file` (`PDF document, version 1.7`)
- [x] E-9 Merged Lane C's UI work from the `Prasad` branch (modular multi-page Streamlit: landing
  page + `/main` console, `theme.py`, `api.py`, `components/`, `views/`, plus `docs/SRS-PRD.md`).
  Clean auto-merge on every file, including `ui/Dockerfile` (both sides' changes were on
  non-overlapping lines — kept the new `COPY` list for `components/`/`views/` *and* the
  BuildKit cache-mount speedup). Verified real, not just merged: rebuilt and ran the actual UI
  container, confirmed both routes serve real 200s, found and fixed one real integration bug
  from the branch-timing gap — `vitals_status()` checked only `events[-1]`, but the backend now
  appends `librarian`/`report_generated` events after `approve`, so a real post-restart state
  could read as generic "healthy" instead of "recovering." Fixed to scan backward for the most
  recent `ask`/`approve`; re-verified live against a real leak → approve cycle, including a case
  where a second, watcher-triggered proposal was genuinely concurrent — confirmed the fix
  correctly reports "awaiting approval" for that real pending state, not a false positive.
- [x] E-10 Refreshed the architecture Artifact for Jaeger/Grafana/reports/the merge (old link
  died mid-session — new URL, see `docs/PROGRESS.md`), and added the same briefing as an in-app
  `/docs` route (`ui/views/docs_page.py`, `ui/components/mermaid.py`) so it's always live with
  the demo. **Actually screenshotted with a real headless Chromium** (installed via
  `npx playwright install chromium` since no browser MCP tool was connected) — diagrams confirmed
  rendering as real SVGs with correct content, not raw text. Found one real, low-risk bug: a
  transient Streamlit "page not found" toast on a cold direct `/docs` URL paste, which clears in
  a few seconds and does **not** appear when navigating via the in-app link (the actual demo
  path) — verified both cases separately.
- [x] E-11 Report-generation UI panel (`ui/components/reports_panel.py`, on the console) —
  context input, generate button, rendered Markdown, Download .md / Download PDF, past-reports
  list. Teammate's original spec called for a sidebar; this app's actual rebuilt layout has no
  sidebar, so it renders as a console section instead. Driven end-to-end with real Playwright
  clicks (not just curl): typed real context into the real textarea, clicked the real button,
  watched the real spinner state, waited out the real two-stage LLM round trip. Found and fixed
  a real bug this way — `st.expander` nested inside another `st.expander` threw
  `StreamlitAPIException` (Streamlit disallows nesting); the backend pipeline itself worked fine
  even while this was broken (report generated, audit went 27→28 events), confirming the bug was
  UI-only. Rebuilt, re-ran the same real click flow, confirmed the full 7-section report renders,
  both download buttons appear, and the past-reports list correctly shows all 4 real reports
  generated across this session's testing.
- [x] E-12 Second watched service, `worker-service` — a genuinely different failure signature
  (`worker_jammed`/`worker_queue_depth` gauges, a stuck-consumer pattern) not a copy of
  target-app's memory leak. Wired into Prometheus scraping, OTel/Jaeger tracing, the watcher
  (`SERVICE_METRIC_CHECKS`, per-service now instead of one shared hardcoded metric name — fixes
  a real bug found while extending it: the old leak check queried `app_leak_bytes` with no job
  filter, harmless with one service but would have mislabeled a second one), `/demo/trigger`,
  `scripts/demo-trigger.sh jam`, the landing page's "try it" buttons (which previously only had
  one, for `/leak` — crash/slow/jam are there now too), and per-container vitals on the console
  (previously a single hardcoded "target-app" strip regardless of which container an event was
  about). Verified fully live: real jam → real agent diagnosis (correctly cites the stuck-queue
  log line and gauges, not a leak) → real approve → real restart → real recovery, and separately
  the proactive watcher catching a jam with zero manual `/ask` calls.

## Demo-ready gate (all must pass)
- [x] Failure injection reliably reproduces on demand — `/leak`, `/slow`, `/crash` all tested
- [x] Copilot correctly names the root cause unprompted — memory leak (cites `app_leak_bytes` +
  OOM log lines), injected latency (cites log line, correctly declines to recommend a restart
  since it's self-resolving), crash (cites exit code + FATAL log line)
- [x] Restart action is blocked until Approve is clicked, and works after — verified for both
  the leak and crash scenarios; `/slow` correctly gets no restart proposal at all
- [x] `audit-log.jsonl` shows the full trail for the demo run — `ask`/`approve` pairs present
  with `ts`, question, answer, and result for each
