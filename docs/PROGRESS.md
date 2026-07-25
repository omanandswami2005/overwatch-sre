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
  updated** for Jaeger/Grafana (both landed after this was published) — refresh before showing it
  to judges.
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
