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
- **Architecture briefing artifact**: published, Chrome-viewable —
  `https://claude.ai/code/artifact/50b05efa-f530-4ef2-888a-1d2540f6891a` (private until shared
  from its own share menu). Covers system diagram, core loop, librarian/wiki split, toolset
  plugin diagram, built-vs-integrated table, modular-monolith/scaling honesty section. **Not yet
  updated** for Jaeger/tracing or (once built) Grafana — do that before showing it to judges if
  those land.
- **Git/GitHub identity**: `omanandswami2005` / `omanandswami2005@gmail.com`, both `gh` and local
  git config. Real Anthropic API key was pasted into chat once — written only to gitignored
  `.env`, user was told to rotate it in the Anthropic Console regardless.

## In progress right now (this session, may be mid-edit)

- **OpenTelemetry tracing → Jaeger** — code complete, **not yet rebuilt/tested**:
  - `target-app/requirements.txt`: added `opentelemetry-distro`,
    `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-instrumentation-fastapi`
    (deliberately unpinned — api/sdk/exporter/instrumentation must resolve to a mutually
    compatible set, safer to let pip pick than hand-pin each and risk a mismatch).
  - `target-app/Dockerfile`: `CMD` now `opentelemetry-instrument uvicorn app:app ...`.
  - `docker-compose.yml`: added `jaeger` service (`jaegertracing/all-in-one:1.76.0`,
    `COLLECTOR_OTLP_ENABLED=true`, ports `16686` UI/Query API + `4317` OTLP gRPC). `target-app`
    gets `OTEL_*` env vars pointing at `http://jaeger:4317`. `backend` gets
    `JAEGER_QUERY_URL=http://jaeger:16686`.
  - `backend/toolsets/jaeger_toolset.py`: new `JaegerToolset`, one tool `query_traces(service,
    lookback_minutes, limit)` — hits Jaeger's Query API `/api/traces`, returns simplified
    trace/span summaries. Registered in `toolsets/__init__.py`, `app.py`'s `_build_registry()`,
    and `toolsets.yaml` (`jaeger: enabled: true`).
  - System prompt updated to mention `query_traces` and when to reach for it (latency /
    "which specific operation is slow" questions).
  - **NOT YET DONE**: `docker compose up --build` to actually rebuild `target-app` with the new
    Dockerfile/requirements, confirm traces actually land in Jaeger, confirm `query_traces`
    returns real data to the agent. Don't claim this works until that's run for real.

- **Grafana dashboard** — just started, mostly not built yet:
  - `grafana/provisioning/datasources/`, `grafana/provisioning/dashboards/`, `grafana/dashboards/`
    directories created, **all still empty**.
  - **STILL TO DO**:
    1. `grafana/provisioning/datasources/datasources.yml` — Prometheus (`uid: prometheus`) +
       Jaeger (`uid: jaeger`) datasources, both `access: proxy`, pointed at the in-network URLs.
    2. `grafana/provisioning/dashboards/dashboards.yml` — file-provider pointing at
       `/var/lib/grafana/dashboards`.
    3. `grafana/dashboards/overwatch.json` — real dashboard, not a stub: panels for
       `app_leak_bytes` (target-app metric), `container_memory_usage_bytes{name="target-app"}`
       and CPU from cadvisor, an `up{job="target-app"}` stat. Must reference datasource by the
       explicit `uid` set above, not an auto-generated one (common provisioning gotcha).
    4. `docker-compose.yml`: add a `grafana` service (`grafana/grafana:13.0.2` — the `grafana-oss`
       repo is being deprecated as of 12.4.0+, use `grafana/grafana` per current Grafana docs),
       port `3000`, mount the two provisioning dirs read-only, `GF_AUTH_ANONYMOUS_ENABLED=true` +
       `GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer` so judges can open `localhost:3000` with zero login
       friction, `depends_on: prometheus, jaeger`.
    5. **Incident annotations on the dashboard** (explicitly requested — "how is the incident
       tracked/triggered" should be visible on the graph, not just in a JSON log): plan is to
       `POST` to Grafana's `/api/annotations` HTTP API from the backend right when a restart
       succeeds (same best-effort, non-blocking pattern as the librarian/Slack triggers in
       `/approve`), using Grafana's default `admin`/`admin` basic auth over the internal Docker
       network (`GF_SECURITY_ADMIN_USER`/`PASSWORD` set explicitly in compose for predictability).
       **Not started** — no code written yet for this specific piece.
  - **NOT YET VERIFIED AT ALL** — no build, no data confirmed flowing into a real dashboard yet.
    Don't tell the user or judges this works until it's actually been loaded in a browser (or
    curled against Grafana's API) and shown to have real data.

## Proposed, discussed, not started

- **Slack bot as a second first-class interface** (user's own design, not mine) — a separate
  `slack-bot` container, pure HTTP client of the existing `/ask` → `/approve/{id}` → `/audit`
  contract, same role as `ui/` today. User's reasoning (sound, worth keeping if this gets built):
  Socket Mode over Events API (no public URL/tunnel needed in Compose), a **separate** container
  rather than in-process in `backend` (failure isolation — a dropped Slack WebSocket shouldn't
  affect the backend or UI), async + background task to satisfy Slack's 3-second ACK requirement
  (ack immediately, run `_run_agent` in the background, deliver the real result via
  `response_url`).
  - **Hard blocker**: needs real Slack credentials (`SLACK_BOT_TOKEN` starting `xoxb-`,
    `SLACK_APP_TOKEN` starting `xapp-`) from a Slack App the user creates at api.slack.com with
    Socket Mode enabled. Cannot be built-and-verified without those — user was explicit: no fake
    testing. If picked up: scaffold the container/code can happen without the tokens, but it is
    **not** "done" or "tested" until run against a real Slack workspace with real tokens.
  - New dependency: `slack-bolt` (Python SDK).

- **Centralized/searchable logs (e.g. Loki)** — user flagged "we have very less logs" as a
  concern. Current state: `get_container_logs` (docker toolset) gives the agent raw container
  stdout on demand, which does functionally satisfy the PS's "logs" leg for diagnosis purposes —
  but there's no aggregated, dashboarded, searchable log store the way Grafana/Jaeger give you
  for metrics/traces. Adding Loki (Grafana Labs' own project, **not** a CNCF project, same
  caveat as Grafana itself) + Promtail/the Docker logging driver would close that visually.
  **Not started, not committed to** — flagged as optional, pending user priority call given time
  left.

- **One-command demo trigger/reset script** — requested ("must need something while giving demo
  to trigger the things again"). `target-app` already exposes `/leak`, `/crash`, `/slow`,
  `/reset` — the primitives exist. What's missing is a convenience wrapper (e.g.
  `scripts/demo-leak.sh` doing reset → leak ×N → print next steps) so a live demo doesn't depend
  on typing raw `curl` commands correctly under pressure. **Not started.**

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
# target-app :8080   prometheus :9090   cadvisor :8081
# backend    :8000   ui :8501           jaeger :16686 (once rebuilt)
# grafana    :3000 (once the service exists in docker-compose.yml)
```

`backend` reloads on code edits via the bind mount — no rebuild needed there. `target-app`
**does** need a rebuild (`docker compose up --build target-app`) to pick up the new OTel
instrumentation, since it has no bind mount / reload set up (only `backend` does).

Compile-check before trusting any Python edit: `python3 -m py_compile backend/app.py
backend/*.py backend/toolsets/*.py` (delete `__pycache__` after — it's gitignored but no need to
leave clutter). `docker compose config --quiet` catches YAML/compose mistakes without starting
anything.
