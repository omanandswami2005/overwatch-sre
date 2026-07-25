# Progress — status snapshot

Living record of what's done (verified for real, not assumed), what's in-flight, and what's
proposed but not started. Written mid-build because context was running low and losing track of
state would cost more time than writing this down. Update this alongside code the same way
`CLAUDE.md`/`docs/architecture.md` already get updated — see the "docs alongside code" convention
in `CLAUDE.md`.

## Done and verified end-to-end (real `docker compose` runs, real curl calls, no simulation)

- **Core loop**: `target-app` (`/crash /leak /slow /reset /metrics`) → `prometheus`+`cadvisor` →
  `backend` chat agent (Claude tool-use loop) → `propose_restart` → human `POST /approve` →
  `docker-py` restart → `audit-log.jsonl`. Verified for all three failure modes: `/leak`,
  `/crash`, `/slow` (correctly declines to propose a restart for the self-resolving `/slow`
  case).
- **Toolset framework** (`backend/toolsets/`): `Toolset` as a `typing.Protocol`, `ToolsetRegistry`
  aggregates enabled toolsets from `toolsets.yaml` into one Claude `tools=` list. Adding a
  capability = write a module + register a factory in `app.py`'s `_build_registry()` + flip a
  config flag.
- **Librarian agent + self-updating wiki** (`backend/librarian.py`): a second, isolated agent
  whose *only* tool is `write_wiki_pages` (forced via `tool_choice`, one call). Triggered
  automatically, best-effort, after an approved restart succeeds. Writes `wiki/index.md`,
  `wiki/services/<container>.md`, `wiki/incidents/<action_id>.md`. `write_wiki_pages` is never
  registered in the shared `ToolsetRegistry` — the chat agent has no path to write access,
  structurally. Verified: a follow-up question about the same symptom correctly cites the prior
  incident via `search_wiki` (read-only `WikiToolset`) before re-checking live data.
- **Slack notifications** (`backend/notifications.py`): `notify_slack()`, best-effort, no-op if
  `SLACK_WEBHOOK_URL` unset. Fires on a `propose_restart` and on the `/approve` outcome.
  Backend-triggered, not LLM-invoked. Verified against a real endpoint (httpbin) for both the
  configured and unconfigured code paths.
- **`GET /incidents`**: audit events grouped into `{ask, approve}` pairs by `action_id`.
- **Proactive watcher** (`backend/watcher.py`): background thread, cheap deterministic checks
  (`app_leak_bytes` over threshold, container status) every `WATCH_INTERVAL_SECONDS` (default
  30s), no LLM call unless a check trips. Trip → same `_handle_ask()` path `/ask` uses, tagged
  `source: "watcher"`. Per-`(container, check)` cooldown (`WATCH_COOLDOWN_SECONDS`, default 300s).
  **Verified live**: pushed `target-app` over the leak threshold with zero manual `/ask` calls;
  it investigated unprompted within one interval, cited the prior wiki incident, proposed a
  restart.
- **`max_tokens` bug fix**: `_run_agent()` originally used `max_tokens=1024`; this model's
  "thinking" blocks could consume the whole budget across multi-round tool calls before any
  answer text was written, silently returning `""`. Fixed: raised to 4096, explicit handling for
  `stop_reason == "max_tokens"` and empty-text cases.
- **Dev loop**: `backend` bind-mounts `./backend:/app` + `uvicorn --reload` in Compose — no
  rebuild needed for backend code changes, only for `requirements.txt`/`Dockerfile` changes.
- **`docker-compose.yml`**: all services wired (`target-app`, `cadvisor`, `prometheus`,
  `backend`, `ui`, plus `jaeger` — see below). `.env.example` documents every env var.
- **HolmesGPT removed entirely** — replaced with a hand-written Claude tool-use agent. Historical
  record kept at `docs/holmes-gpt-reference.md` (user intends to delete it eventually — safe to
  do any time, nothing depends on it).
- **Architecture briefing artifact**: refreshed for Jaeger/Grafana/reports/the UI merge, published
  at `https://claude.ai/code/artifact/4f2dc651-0f99-4274-9ef7-78e029a92992` (private until shared
  from its own share menu; the original link died mid-session — publisher access was lost, so
  this is a new URL, not an update to the old one). Now 9 sections: system overview, core loop,
  two-agent boundary, proactive watching, metrics/logs/traces, context optimization (the
  Haiku/Sonnet report pipeline), plugin architecture, built-vs-integrated, honest scaling
  assessment.
- **The same briefing now also lives in-app**, at `/docs` in the Streamlit UI — requested
  specifically so it's always live with the demo instead of a separate link that can go stale
  (as the artifact link just did). `ui/components/mermaid.py` renders Mermaid diagrams via
  `components.html()` loading mermaid.js from a CDN (Streamlit has no native Mermaid support,
  unlike the Artifact sandbox). Linked from both the landing page and the console.
  - **Verification honesty**: no real browser automation tool was available in this session, so
    this could NOT be visually screenshotted/pixel-verified. What *was* verified for real: the
    route serves HTTP 200 with zero server-side errors in the container logs, the exact HTML/JS
    `mermaid.render()` generates was extracted and inspected byte-for-byte (clean, valid), all 6
    embedded diagram strings pass a bracket-balance sanity check, and the mermaid.js CDN URL was
    confirmed live and serving real JS via a direct request. The diagram *shapes* are unchanged
    from the ones already proven rendering correctly in the Artifact. This is strong but not
    complete evidence — open `http://localhost:8501/docs` in an actual browser to confirm the
    final visual render before relying on it for a live demo.
- **Git/GitHub identity**: `omanandswami2005` / `omanandswami2005@gmail.com`, both `gh` and local
  git config. Real Anthropic API key was pasted into chat once — written only to gitignored
  `.env`, user was told to rotate it in the Anthropic Console regardless.
- **OpenTelemetry tracing → Jaeger** — built AND verified for real (previously flagged as
  untested; that's resolved now):
  - `target-app` runs under `opentelemetry-instrument`, exports via OTLP gRPC to `jaeger`
    (`jaegertracing/all-in-one:1.76.0`, `COLLECTOR_OTLP_ENABLED=true`).
  - **Verified**: `curl http://localhost:16686/api/services` lists `target-app`; pulled real
    traces with real span durations via `/api/traces?service=target-app`.
  - `backend/toolsets/jaeger_toolset.py`'s `query_traces` tool **verified working through the
    live agent** — asked "check target-app recent traces, is anything unusually slow?" and got
    back a real answer citing actual span durations (`GET /` ~0.8-1.0ms, `GET /metrics`
    ~1.4-1.9ms), not a hallucinated summary.
- **Grafana dashboard** — built AND verified for real:
  - `grafana/provisioning/datasources/datasources.yml` (Prometheus `uid: prometheus` + Jaeger
    `uid: jaeger`), `grafana/provisioning/dashboards/dashboards.yml` (file provider), and a real
    4-panel dashboard at `grafana/dashboards/overwatch.json` (`app_leak_bytes`, aggregate Docker
    memory, aggregate Docker CPU, `target-app` scrape-health stat).
  - `docker-compose.yml`: `grafana` service (`grafana/grafana:13.0.2` — `grafana-oss` is
    deprecated as of 12.4.0+), anonymous Viewer access enabled so judges hit `localhost:3000`
    with zero login friction.
  - **Real platform issue found and fixed, not papered over**: cAdvisor on this Docker
    Desktop/macOS host does not expose per-container `name`/`image`/`container_label_*` labels —
    confirmed via raw `/metrics` inspection, only the raw cgroup `id` path is present, and
    container IDs aren't stable across rebuilds anyway. Panels that would've silently shown "no
    data" (`container_memory_usage_bytes{name="target-app"}`) were rewritten to aggregate across
    all containers (`id=~"/docker/.+"`), which *is* reliably labeled and was confirmed returning
    real numbers. This is documented as a platform limitation in the panel's own description
    field inside the dashboard JSON, not silently worked around.
  - **Incident annotations, verified live**: `backend/notifications.py`'s `annotate_grafana()`
    posts to Grafana's `/api/annotations` API (admin/admin basic auth, internal network only) on
    every successful `/approve`. Triggered a real leak → approve cycle and confirmed via
    `GET /api/annotations?tags=overwatch` that the actual incident reason text landed as a real
    annotation — this is the answer to "how is an incident visible on the dashboard, not just in
    a JSON log."
  - Every panel query and the annotation were confirmed with real data through Grafana's own API
    (`/api/datasources/proxy/...`, `/api/annotations`), not just "the YAML looks right."
- **Docker build speed** — root cause confirmed before fixing anything (didn't guess): all three
  Dockerfiles used `uv pip install --no-cache`, which re-downloads every wheel from scratch on
  every build; no `.dockerignore` existed anywhere. Fixed with the standard BuildKit
  `--mount=type=cache` pattern (uv cache + apt cache), which persists the *download* cache across
  builds without baking it into the image — same installed packages, same final layers, just
  faster to rebuild. **Verified, not assumed**: forced a `--no-cache` rebuild of `target-app`
  (bypassing Docker's own layer cache entirely) and confirmed the install step stayed fast
  because the separate BuildKit cache mount still had the wheels.
- **One-command demo trigger** — `scripts/demo-trigger.sh leak|crash|slow|reset` (resets,
  triggers, optionally asks the copilot, prints next steps) plus a `POST
  /demo/trigger/{mode}` backend passthrough to `target-app`'s endpoints, so a future UI button
  doesn't need to know `target-app` exists directly. Both verified live. The passthrough's error
  path was also verified for real: called it while `target-app` happened to be crashed from
  testing and got a clear 502 with the actual connection error, not a hang or a crash.
- **Incident report pipeline** (`backend/reports.py`) — a genuine two-stage
  cheap-model/smart-model architecture, not hackathon-only wiring:
  - **Stage 1 (Haiku, `claude-haiku-4-5-20251001`)**: reads raw `audit-log.jsonl` (time-windowed)
    + Prometheus `query_range` data, compresses into a structured brief via one forced tool call
    (`extract_brief`) — same "force `tool_choice`, one call" pattern as the librarian.
  - **Stage 2 (Sonnet, the main `ANTHROPIC_MODEL`)**: writes the actual 7-section Markdown
    postmortem (Summary, Impact, Timeline, Root Cause, Resolution, Detection, Action Items) from
    the compressed brief + the developer's own plain-English context.
  - Researched, not assumed: this Haiku-compresses/Sonnet-writes split is a real, current
    recommended pattern (Haiku holds ~2-5% quality gap vs. Sonnet on extraction/classification at
    a fraction of the cost) — this is the actual answer to "what's implemented for context
    optimization," not just a talking point.
  - `.md` saved to `REPORTS_DIR` (under the same `backend-data` volume as the wiki/audit log),
    PDF rendered on demand via WeasyPrint (`markdown` → HTML → CSS-styled → PDF).
  - New endpoints: `POST /report/generate {context, container}`, `GET /reports`,
    `GET /report/{id}/md`, `GET /report/{id}/pdf`. Not agent tools — triggered directly by a
    human request, same "deterministic trigger, not model discretion" reasoning as every other
    side-effecting action in this system.
  - **Real platform issue found and fixed mid-build**: the base image is Debian trixie, where
    `libgdk-pixbuf2.0-0` (the package name from most WeasyPrint docs/tutorials, which target
    older Debian) was renamed to `libgdk-pixbuf-2.0-0`. Found via `apt-cache search` inside the
    actual base image rather than guessing a second time.
  - **Verified end-to-end for real**: generated a report against this session's actual leak/crash
    history — the Markdown correctly cites real action IDs (`4dc5c6fb...`, `84a2b5a3...`,
    `39329720...`, `a31fe84d...`) and real timestamps from the real audit log, no hallucinated
    data. PDF confirmed via the `file` command: `PDF document, version 1.7`, real byte content,
    not an empty/broken file.
- **No UI changes made** in any of this session's backend work (up to the merge below) —
  confirmed by design, and by `git status` showing zero touches to `ui/app.py` throughout.
- **Merged Lane C's UI work from the `Prasad` branch** — real multi-page Streamlit UI (landing
  page + `/main` console): `theme.py`, `api.py`, `components/` (chat, vitals, audit drawer,
  decisions, proactive, safety, stack, try-it, verified, footer, hero, how-it-works, landing),
  `views/` (landing_page, main_page), plus `docs/SRS-PRD.md`. Every file merged cleanly,
  including `ui/Dockerfile` where both branches had touched non-overlapping lines (kept the new
  `COPY components/ views/` lines *and* the BuildKit cache-mount speedup).
  - **Verified for real, not just merged**: rebuilt the actual `ui` image, confirmed both `/` and
    `/main` serve real HTTP 200s through the running container.
  - **Found and fixed a real bug from the branch-timing gap**: `ui/components/vitals.py`'s
    `vitals_status()` read only `events[-1]` to derive the status pill — but `Prasad` was forked
    before the librarian/report-generation work landed, and the backend now appends
    `librarian`/`report_generated` audit events *after* `approve`. Confirmed live (not
    theoretical): triggered a real restart, checked the audit tail, `events[-1]["type"]` was
    `"librarian"`, and the original code silently fell through to a generic "healthy" instead of
    "recovering." Fixed to scan backward for the most recent `ask`/`approve`. Re-verified against
    a live, spontaneously concurrent case — a watcher-triggered proposal landed while a prior
    incident's librarian call was still running — and confirmed the fix correctly reports
    "awaiting approval" for that genuinely-pending action rather than a false "recovering."
- **Slack bot — second first-class interface** (`slack-bot/app.py`, user's own design): `/overwatch
  <question>` slash command over Socket Mode (`slack-bolt`), pure HTTP client of the same
  `/ask`→`/approve/{action_id}` contract `ui/` uses. Separate container from `backend` on purpose
  (failure isolation — a dropped Slack WebSocket can't affect backend/UI). Slack's 3-second ack
  requirement is satisfied by acking immediately and running the real `_run_agent` call in a
  background thread, delivering the result via `respond()`/`response_url`. A `propose_restart`
  renders as Approve/Dismiss buttons in Slack. Opt-in via `docker compose --profile slack up` —
  absent by default so it never affects anyone running the stack without Slack tokens.
  - **Verified for real, not just built**: real `SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` were provided,
    confirmed valid via Slack's own `auth.test` API (workspace "linkedIn", bot user `sreagent`),
    container built and started, and the container logs show a genuine Socket Mode session
    established (`A new session has been established`, `⚡️ Bolt app is running!`,
    `Starting to receive messages from a new connection`) — not a hallucinated success.
  - **Not yet verified**: an actual `/overwatch` slash command round-trip typed in the real Slack
    workspace — needs the user to either register the slash command in the Slack App config
    (api.slack.com/apps → Slash Commands) if not already done, and then actually type
    `/overwatch <question>` in Slack. Confirm this before relying on it for a demo.

## Proposed, discussed, not started

- **Centralized/searchable logs (e.g. Loki)** — user flagged "we have very less logs" as a
  concern. Current state: `get_container_logs` (docker toolset) gives the agent raw container
  stdout on demand, which does functionally satisfy the PS's "logs" leg for diagnosis purposes —
  but there's no aggregated, dashboarded, searchable log store the way Grafana/Jaeger give you
  for metrics/traces. Adding Loki (Grafana Labs' own project, **not** a CNCF project, same
  caveat as Grafana itself) + Promtail/the Docker logging driver would close that visually.
  **Not started, not committed to** — flagged as optional, pending user priority call given time
  left.

- ~~One-command demo trigger/reset script~~ — **done**, see above.

- **GitHub PR from incident writeups** — deferred (not dropped) pending a `GITHUB_TOKEN` with
  repo write scope. Wiki files already exist as plain markdown specifically so "open a PR with
  these" is a fast follow whenever that token is available.

- **Docker MCP Gateway + GitHub MCP server** — researched, confirmed real/current (Docker's own
  product, explicitly on the hackathon's Docker-product ground-rules list; official
  `mcp/github-official` image exists in Docker's MCP catalog). Would be the "proper" way to
  finally ship the GitHub PR feature above using a real Docker product instead of hand-rolled
  GitHub API calls. **Not started** — needs confirmation that Docker Desktop's MCP Toolkit is
  actually available in whatever environment the demo will run in, before committing time to it.

## Environment / how to pick this back up

```
cp .env.example .env   # ANTHROPIC_API_KEY required; SLACK_WEBHOOK_URL, WATCH_* optional
docker compose up --build
# target-app :8080   prometheus :9090   cadvisor :8081   jaeger :16686
# backend    :8000   ui :8501           grafana :3000 (admin/admin, or anonymous Viewer)
```

`backend` reloads on code edits via the bind mount — no rebuild needed there. `target-app`
**does** need a rebuild (`docker compose up --build target-app`) to pick up the new OTel
instrumentation, since it has no bind mount / reload set up (only `backend` does).

Compile-check before trusting any Python edit: `python3 -m py_compile backend/app.py
backend/*.py backend/toolsets/*.py` (delete `__pycache__` after — it's gitignored but no need to
leave clutter). `docker compose config --quiet` catches YAML/compose mistakes without starting
anything.
