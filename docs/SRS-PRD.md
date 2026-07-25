# Software Requirements Specification & Product Requirements Document

## Overwatch-SRE — an LLM Copilot for Container Health

| | |
|---|---|
| **Document version** | 1.0 |
| **Status** | Draft — reflects implemented state as of this read |
| **Project phase** | Hackathon build (6.5-hour time box) |
| **Owning repo docs** | [README.md](../README.md) · [architecture.md](architecture.md) · [CHECKLIST.md](CHECKLIST.md) · [UI-DESIGN.md](UI-DESIGN.md) |

This document merges a Software Requirements Specification (IEEE 830-style: functional/
non-functional requirements, interfaces, constraints) with a Product Requirements Document
(problem statement, personas, success metrics, scope) into one artifact, since the project is
small enough that maintaining them separately would fragment, not clarify, the picture. Where
this document and the narrative docs above disagree, the narrative docs plus the actual code
(`backend/app.py`, `target-app/app.py`, `ui/app.py`, `docker-compose.yml`) are the source of
truth — this SRS/PRD is a structured restatement of them, not a new source of intent.

---

## 1. Introduction

### 1.1 Purpose

Overwatch-SRE lets an on-call engineer ask a single chat window "why is this service
unhealthy?" instead of cross-referencing a Grafana dashboard, a PromQL query box, `docker
logs`, and a runbook wiki by hand. The system correlates live Prometheus/cAdvisor metrics and
Docker container state, produces a plain-language root-cause diagnosis, and — only after an
explicit human approval click — restarts the offending container. Every step is appended to an
append-only audit log.

### 1.2 Problem statement

Diagnosing a degraded service normally means a human manually correlating several
disconnected tools (metrics dashboard, log viewer, container inspector) under time pressure,
then taking a remediation action with no single record tying the diagnosis to the action taken.
This is slow, error-prone under stress, and leaves a fragmented (or absent) audit trail.

### 1.3 Product goal

Compress "notice something's wrong → correlate metrics + logs → decide → act → record what
happened" into one conversational flow, without removing the human from the one step that has
real blast radius (restarting a container).

### 1.4 Scope

**In scope** — exactly four components, wired together with Docker Compose:

1. `target-app` — a FastAPI demo service with on-demand failure injection.
2. `prometheus` + `cadvisor` — off-the-shelf metrics collection, config only.
3. `backend` — a FastAPI service running a Claude tool-use agent loop, a human-gated restart
   action, and a JSONL audit log.
4. `ui` — a Streamlit chat client with zero business logic of its own.

**Out of scope** (see [§10](#10-out-of-scope--non-goals) for the full list and rationale):
authentication/authorization, multi-cluster or multi-host support, Kubernetes, any database
beyond the flat audit-log file, monitoring of more than the one demo service, and any tool that
lets the LLM mutate system state directly.

### 1.5 Definitions, acronyms

| Term | Meaning |
|---|---|
| Agent / copilot | The Claude tool-use loop in `backend/app.py`'s `_run_agent()` |
| Toolset | A self-contained module (`backend/toolsets/*.py`) bundling related tool schemas + their execution, matching the `Toolset` protocol in `toolsets/base.py` |
| Proposed action | A `{type, container, reason}` dict recorded by the `propose_restart` tool, held in the in-memory `_pending_actions` dict until approved or abandoned |
| Action ID | A UUID minted per proposed action, the only way `POST /approve/{action_id}` can be invoked |
| Audit event | One JSON line appended to `audit-log.jsonl`; types are `ask`, `ask_error`, `approve` |
| PromQL | Prometheus Query Language, used by the `query_prometheus` tool |
| SRE | Site Reliability Engineering |

### 1.6 References

[README.md](../README.md) (pitch, tech stack, demo script) · [architecture.md](architecture.md)
(system + sequence diagrams, design decisions) · [CHECKLIST.md](CHECKLIST.md) (task breakdown,
demo-ready gate) · [UI-DESIGN.md](UI-DESIGN.md) (visual spec) ·
[holmes-gpt-reference.md](holmes-gpt-reference.md) (superseded framework, historical record) ·
[CLAUDE.md](../CLAUDE.md) (contributor orientation).

---

## 2. Overall description

### 2.1 Product perspective

Overwatch-SRE is a standalone, self-contained demo system — five containers on one Docker
Compose network, no external dependencies besides the Anthropic API. It is not a plugin to an
existing observability stack; it *is* the stack, scoped down to one observed service.

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

See [architecture.md §System overview](architecture.md#system-overview) for the full annotated
diagram and [§Deployment topology](architecture.md#deployment-topology) for the container/port/
volume layout.

### 2.2 Product functions (summary)

1. Continuously scrape application- and container-level metrics from the observed service.
2. Accept a natural-language question about system health and answer it by autonomously
   querying metrics, container status, and container logs.
3. When the diagnosis warrants it, propose a specific remediation (container restart) with a
   stated reason, without executing it.
4. Execute the proposed remediation only when a human explicitly approves it via a dedicated
   endpoint tied to that specific proposal.
5. Record every question, diagnosis, proposal, and approval outcome to an append-only,
   human-readable audit log.
6. Present all of the above through a single chat interface with an at-a-glance health
   indicator, requiring no client-side business logic.

### 2.3 User classes and characteristics

| User class | Description | Primary needs |
|---|---|---|
| On-call engineer (primary persona) | Investigates and responds to an incident on the observed service | Fast, accurate root-cause answers; a low-friction, low-risk way to remediate; confidence the system won't act without them |
| Hackathon judge / evaluator | Assesses the demo in a few minutes | A single coherent narrative (one chat window vs. four dashboards), a visible safety gate, a visible audit trail |
| Developer / contributor (Lanes A/B/C) | Builds and extends the four components | Clear API contract between `backend` and `ui`; toolsets addable without touching the agent loop |

### 2.4 Operating environment

- Docker Engine with Compose v2, one host, Linux containers (Windows/Mac dev hosts run this via
  Docker Desktop).
- `backend` requires `/var/run/docker.sock` mounted read-write to restart sibling containers.
- Outbound HTTPS access to the Anthropic API (`api.anthropic.com`) from the `backend` container.
- No GPU, no local model runtime required (explicitly rejected — see
  [§9 Design constraints](#9-design-constraints-and-rationale)).

### 2.5 Assumptions and dependencies

- A valid `ANTHROPIC_API_KEY` is available in the environment (via `.env`, consumed by
  `docker-compose.yml`).
- The Docker daemon socket is available to mount into `backend`; the host user has permission to
  do so.
- Prometheus's default scrape/query semantics are sufficient (no long-term storage, no alerting
  rules — those are explicitly out of scope).
- The `anthropic` Python SDK (`>=0.39.0,<1.0.0`) tool-use API surface matches what
  `_run_agent()` expects — flagged as unverified against a live install in
  [architecture.md §Known gaps](architecture.md#known-gaps).

---

## 3. Stakeholders & success metrics

| Stakeholder | Interest |
|---|---|
| Hackathon team (Lanes A/B/C) | Ship a working, demoable system inside 6.5 hours |
| Judges | See a genuinely useful safety-boundary pattern, not "chatbot wrapper around a dashboard" |
| Future on-call engineer (hypothetical real usage) | Trustworthy diagnosis, no surprise mutations |

### Success metrics (demo-oriented, per [CHECKLIST.md §Demo-ready gate](CHECKLIST.md#demo-ready-gate))

- Failure injection (`/crash`, `/leak`, `/slow`) reliably reproduces on demand.
- The copilot names the correct root cause (memory leak / crash / slowness) **unprompted** —
  i.e., without the human first telling it what's wrong.
- The restart action is provably blocked until a human clicks **Approve restart**, and succeeds
  once clicked.
- `audit-log.jsonl` shows a complete, readable trail for the full demo run (ask → diagnosis →
  approve → result).

There is no quantitative SLA target (latency, uptime) for this hackathon build — see
[§6.2](#62-performance) for the qualitative bar instead.

---

## 4. External interface requirements

### 4.1 User interface

Governed in full by [UI-DESIGN.md](UI-DESIGN.md); summarized here for completeness. Single-
screen Streamlit app, dark theme, three zones:

1. **Header bar** — product name + live connection indicator (teal = backend reachable, red =
   not, driven by whether `GET /audit` succeeds).
2. **Vitals strip** — one row per watched service (`target-app` only, for this build) showing
   `healthy` / `degraded` / `down`, derived from the latest `/audit` entry (`ui/app.py`'s
   status-derivation logic — see [§5.4](#54-fr-4--vitals-status-derivation)).
3. **Triage chat** — native `st.chat_message` thread; the copilot's diagnosis renders inline,
   and when a `recommended_action` is present, an inline card with **Approve restart** /
   **Dismiss** buttons appears attached to that message.
4. **Audit drawer** — collapsed `st.expander`, one monospace line per audit event, newest first.

Copy strings (exact wording for empty state, button labels, confirmations, error states) are
canonical in [UI-DESIGN.md §Copy](UI-DESIGN.md#copy-write-in-the-interfaces-voice-not-a-persons)
— UI implementation must not paraphrase them.

### 4.2 API contract (backend ↔ ui)

This is the load-bearing interface in the system — `ui/app.py` is a pure client against it, and
nothing about the contract may change without updating both sides (per
[CLAUDE.md](../CLAUDE.md#api-contract-backend--ui)).

| Endpoint | Method | Request | Response | Notes |
|---|---|---|---|---|
| `/ask` | POST | `{"question": string}` | `{"answer": string, "recommended_action": object \| null, "action_id": string \| null}` | Runs the full agent loop synchronously; blocks until Claude returns a final text answer or `MAX_TOOL_ROUNDS` (6) is exhausted |
| `/approve/{action_id}` | POST | *(none — id in path)* | `{"status": "restarted" \| "failed", "container": string, "error"?: string}` | 404 if `action_id` is unknown or already resolved; the *only* code path that calls `container.restart()` |
| `/audit` | GET | *(none)* | `list[object]` — every logged event, oldest first, each with a `ts` (unix float) | Reads the whole file, no pagination |
| `/healthz` | GET | *(none)* | `{"status": "ok"}` | Liveness only, no dependency checks |

`recommended_action`, when present, has the shape `{"type": "restart_container", "container":
string, "reason": string}`.

### 4.3 Hardware/software interfaces

- **Prometheus HTTP API** (`GET /api/v1/query`) — consumed by `PrometheusToolset` via
  `requests`, base URL from `PROMETHEUS_URL` (default `http://prometheus:9090`).
- **Docker Engine API** — consumed by `DockerToolset` and the `/approve` handler via `docker-py`
  (`docker.from_env()`), requires the Unix socket mount.
- **Anthropic Messages API** — consumed via the `anthropic` Python SDK, model id from
  `ANTHROPIC_MODEL` (default `claude-sonnet-5`), auth via `ANTHROPIC_API_KEY`.
- **cAdvisor** — scraped by Prometheus only; `backend` never talks to it directly.

---

## 5. Functional requirements

Each requirement is tagged with an ID, the owning component, and a Must/Should priority. "Must"
requirements gate the demo-ready checklist; "Should" requirements are already implemented but
not release-blocking for the hackathon scope.

### 5.1 FR-1 — Failure injection (`target-app`)

| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | `GET /crash` hard-exits the process (`os._exit(1)`) to simulate a crash loop | Must |
| FR-1.2 | `GET /leak` appends a 10MB in-memory chunk per call and exposes cumulative leaked bytes via the `app_leak_bytes` Prometheus gauge | Must |
| FR-1.3 | `GET /slow` forces a 3-second response on that call and flags "slow mode" (visible in `GET /`) for the following 120 seconds | Must |
| FR-1.4 | `GET /reset` clears leak state and slow-mode flag, returning the service to a clean baseline | Must |
| FR-1.5 | `GET /metrics` exposes all metrics in Prometheus exposition format | Must |
| FR-1.6 | `GET /` reports current `leaking`, `leaked_bytes`, and `slow_mode` state for quick manual inspection | Should |

### 5.2 FR-2 — Metrics collection (`prometheus` + `cadvisor`)

| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | Prometheus scrapes `target-app:8080/metrics` and `cadvisor:8080/metrics` (job names `target-app`, `cadvisor`) | Must |
| FR-2.2 | Scrape interval is 5 seconds, so metric changes (e.g., a leak) are visible to the agent within one scrape cycle | Must |
| FR-2.3 | No custom Prometheus code — configuration only (`prometheus/prometheus.yml`) | Must |

### 5.3 FR-3 — Diagnosis agent (`backend`)

| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | `POST /ask` accepts a free-text `question` and returns a final natural-language `answer` | Must |
| FR-3.2 | The agent loop (`_run_agent`) calls the Anthropic Messages API with a fixed system prompt and the full set of registered tool schemas, executing whichever tools Claude requests and feeding results back, for up to `MAX_TOOL_ROUNDS` (6) rounds | Must |
| FR-3.3 | The agent has access to `query_prometheus` (run an arbitrary PromQL instant query) | Must |
| FR-3.4 | The agent has access to `get_container_status` (running/exited, health, restart count, last exit code) | Must |
| FR-3.5 | The agent has access to `get_container_logs` (tail of a named container's logs, default 50 lines) | Must |
| FR-3.6 | The agent has access to `propose_restart(container, reason)`, which **only** records a recommendation — it must never call `container.restart()` or any other mutating Docker operation | Must |
| FR-3.7 | If the loop exhausts `MAX_TOOL_ROUNDS` without a final text answer, the system returns a graceful fallback message ("Investigation took too many steps — try a narrower question.") rather than an error | Must |
| FR-3.8 | Every tool call result (including errors) is fed back into the conversation as a `tool_result` block so the agent can adapt its next step | Must |
| FR-3.9 | Toolsets are pluggable: enabling/disabling a toolset (`prometheus`, `docker`, `remediation`) is controlled by `backend/toolsets.yaml` without code changes to the agent loop | Should |
| FR-3.10 | A toolset failure (e.g., container not found) is caught by the registry and surfaced to the model as `{"error": ...}` rather than crashing the request | Must |

### 5.4 FR-4 — Propose → approve → execute gate (`backend`)

This is the safety-critical core of the system — see [§7](#7-safety-requirements-the-human-in-the-loop-gate) for the dedicated treatment.

| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | When `propose_restart` is called during a loop, `/ask`'s response includes a non-null `recommended_action` (`{type, container, reason}`) and a freshly minted `action_id` (UUID4) | Must |
| FR-4.2 | The proposed action is held only in server memory (`_pending_actions`), keyed by `action_id`, until resolved | Must |
| FR-4.3 | `POST /approve/{action_id}` is the **only** code path in the entire system that calls `docker-py`'s `container.restart()` | Must |
| FR-4.4 | `POST /approve/{action_id}` with an unknown or already-resolved `action_id` returns HTTP 404 and performs no action | Must |
| FR-4.5 | A successful restart returns `{"status": "restarted", "container": ...}`; a failed one returns `{"status": "failed", "container": ..., "error": ...}` without raising an unhandled exception | Must |
| FR-4.6 | An approved (or resolved) `action_id` is removed from `_pending_actions`, so it cannot be approved twice | Must |
| FR-4.7 | Declining to approve (no call to `/approve/{action_id}`) leaves the action permanently unexecuted — there is no timeout-triggered auto-execution | Must |

### 5.5 FR-5 — Audit logging (`backend`)

| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | Every `/ask` call appends one `type: "ask"` event with `question`, `answer`, `action_id`, and `recommended_action` | Must |
| FR-5.2 | Every `/ask` call that raises an exception appends one `type: "ask_error"` event with `question` and `error`, then returns HTTP 502 | Must |
| FR-5.3 | Every `/approve/{action_id}` call (successful or failed restart) appends one `type: "approve"` event with `action_id`, the original `action`, and the `result` | Must |
| FR-5.4 | Every audit event carries a `ts` (unix timestamp, float) set at write time | Must |
| FR-5.5 | The audit log is a flat, append-only JSONL file at a configurable path (`AUDIT_LOG_PATH`, default `/data/audit-log.jsonl`), volume-mounted so it survives container restarts | Must |
| FR-5.6 | `GET /audit` returns the full parsed list of events, oldest first; an absent file returns an empty list rather than an error | Must |

### 5.6 FR-6 — UI (`ui`)

| ID | Requirement | Priority |
|---|---|---|
| FR-6.1 | The UI is a pure HTTP client against `POST /ask`, `POST /approve/{action_id}`, and `GET /audit` — it makes no independent judgment about health status or recommended actions beyond deriving the vitals-strip label from the latest audit event | Must |
| FR-6.2 | Submitting a question via `st.chat_input` appends it to the visible history, calls `/ask`, and renders the returned answer as a new chat message | Must |
| FR-6.3 | If a chat message carries a `recommended_action` and `action_id` and is not yet `resolved`, an inline card renders with **Approve restart** and **Dismiss** buttons | Must |
| FR-6.4 | Clicking **Approve restart** calls `POST /approve/{action_id}`, shows a success/error toast, and marks the message `resolved` so the buttons don't render again | Must |
| FR-6.5 | Clicking **Dismiss** marks the message `resolved` locally without calling the backend — the `action_id` simply expires unused server-side | Must |
| FR-6.6 | The vitals strip shows `degraded`/`awaiting approval` when the latest audit event is an `ask` with a `recommended_action`, `healthy`/`recovering` when the latest event is a successful `approve`, and `down`/`backend unreachable` when `/audit` cannot be reached; otherwise `healthy` | Must |
| FR-6.7 | If the backend is unreachable, the UI shows the exact copy *"Can't reach the backend. Check `docker compose ps` and retry."* rather than a raw exception | Must |
| FR-6.8 | The audit drawer renders every event as a monospace line, newest first, inside a collapsed-by-default expander labeled with the event count | Must |

---

## 6. Non-functional requirements

### 6.1 Security

- **NFR-SEC-1 (Must).** The LLM must never be given a tool that directly mutates system state.
  All tools exposed to Claude (`query_prometheus`, `get_container_status`,
  `get_container_logs`, `propose_restart`) are read-only or proposal-only by construction — see
  [§7](#7-safety-requirements-the-human-in-the-loop-gate).
- **NFR-SEC-2 (Must).** The one mutating operation in the system (`docker restart`) lives in
  hand-written code (`/approve/{action_id}`) outside any tool the model can invoke, and requires
  a human-originated HTTP call carrying a specific, previously-issued `action_id`.
- **NFR-SEC-3 (Should).** Secrets (`ANTHROPIC_API_KEY`) are supplied via environment variables /
  `.env`, never hardcoded or logged. The audit log must not record the API key or raw request
  headers.
- **NFR-SEC-4 (Accepted risk, hackathon scope).** No authentication/authorization on any
  endpoint — `/ask`, `/approve/{action_id}`, and `/audit` are open to anything on the Compose
  network / exposed host ports. Acceptable for a single-host demo; would be a blocking gap for
  any real deployment (see [§10](#10-out-of-scope--non-goals)).
- **NFR-SEC-5 (Should).** The Docker socket mount into `backend` (`/var/run/docker.sock`) grants
  broad Docker-daemon control; scope is currently trusted-network-only. A production hardening
  pass would scope this via the Docker API's authorization plugins or a proxy that only permits
  `restart` on an allow-listed container name.

### 6.2 Performance

- **NFR-PERF-1 (Should).** `POST /ask` should resolve within the UI's client timeout (95s,
  `ui/app.py`); this bounds `MAX_TOOL_ROUNDS` × (Claude round-trip + one tool call) to a demo-
  acceptable latency. No stricter SLA is defined for the hackathon build.
  `POST /approve/{action_id}` should resolve within its client timeout (15s), matching
  `container.restart(timeout=10)`'s own internal bound.
- **NFR-PERF-2 (Should).** Prometheus scrape interval (5s) should be short enough that a
  triggered failure (e.g., `/leak`) is reflected in metrics before a human finishes asking the
  copilot about it.

### 6.3 Reliability & availability

- **NFR-REL-1 (Must).** A tool-call failure (e.g., querying a nonexistent container) must not
  crash `/ask` — it is caught by `ToolsetRegistry.call()` and returned to the model as
  `{"error": ...}`, allowing the agent to adapt or explain the limitation in its final answer.
- **NFR-REL-2 (Must).** An `/ask` failure at the top level (e.g., Anthropic API error) must
  still be recorded to the audit log (`ask_error`) before the error is surfaced to the caller.
- **NFR-REL-3 (Should).** The audit log volume must persist across `backend` container restarts
  (satisfied by the named Docker volume `audit-log`).
- **NFR-REL-4 (Accepted risk).** `_pending_actions` is in-memory only — a `backend` restart
  between proposal and approval silently invalidates any outstanding `action_id` (the UI will
  surface this as a 404 on approve). Acceptable given the demo's single-session usage pattern.

### 6.4 Usability

- **NFR-USE-1 (Must).** The entire interaction surface is one screen, no navigation — per
  [UI-DESIGN.md](UI-DESIGN.md)'s "one interface, not four" thesis.
- **NFR-USE-2 (Must).** Status must never be conveyed by color alone — every status has a paired
  plain-word label (`healthy` / `degraded` / `down`), per
  [UI-DESIGN.md §Copy](UI-DESIGN.md#copy-write-in-the-interfaces-voice-not-a-persons).
- **NFR-USE-3 (Should).** Visible focus states on the Approve/Dismiss buttons (accessibility
  baseline called out explicitly in UI-DESIGN.md even under time pressure).

### 6.5 Maintainability & extensibility

- **NFR-MAINT-1 (Must).** Adding a new tool/capability must not require touching the agent loop
  in `app.py` — it requires only a new module matching the `Toolset` protocol
  (`backend/toolsets/base.py`), a registration line in `_build_registry()`, and a flag in
  `toolsets.yaml`.
- **NFR-MAINT-2 (Should).** All three Python services install dependencies via `uv`, never bare
  `pip`, for consistent, fast, repeatable builds across repeated container rebuilds.
- **NFR-MAINT-3 (Should).** The `backend`↔`ui` HTTP contract (§4.2) is the seam between lanes —
  changes to it must be reflected on both sides in the same change.

### 6.6 Portability

- **NFR-PORT-1 (Must).** Everything runs via `docker compose up --build` on any Docker-Compose-
  capable host; no cloud-specific or OS-specific dependencies beyond a mountable Docker socket.
- **NFR-PORT-2 (Must).** No GPU or local model runtime dependency — Claude is called over HTTPS,
  so behavior is identical on Intel/Apple Silicon/ARM hosts.

---

## 7. Safety requirements: the human-in-the-loop gate

This is the one piece of genuinely custom logic in the project and the primary thing this SRS
must specify unambiguously, since it is also the primary safety claim of the whole system.

**Requirement (Must, non-negotiable):** at no point may the LLM's own tool-calling ability
result in a container being restarted, stopped, or otherwise mutated, under any input,
prompt, or model behavior.

This is enforced structurally, not by prompting:

1. Every tool schema the agent can invoke is either genuinely read-only (`query_prometheus`,
   `get_container_status`, `get_container_logs` — backed by `read_only = True` toolsets) or
   proposal-only (`propose_restart`, `read_only = False` by declared *intent* but whose `call()`
   implementation only returns a status dict — it never touches `docker_client`).
2. `container.restart()` appears exactly once in the codebase, inside `POST
   /approve/{action_id}` in `backend/app.py` — a route with no tool schema, unreachable by any
   sequence of model tool calls.
3. `POST /approve/{action_id}` can only succeed against an `action_id` that was minted by a
   prior `/ask` call *and* is still present in `_pending_actions` — i.e., it must correspond to
   a proposal the agent actually made, and can only be consumed once.
4. The UI never auto-clicks Approve and has no code path that calls `/approve/{action_id}`
   except in direct response to a user click event on that exact button.

**Verification approach:** because this is a structural guarantee, it should be checked by
inspection (confirm no tool schema's `call()` implementation reaches a mutating Docker
operation) rather than by testing every possible model output — the guarantee holds regardless
of what the model decides to do, by construction. See [§8.4](#84-security-review) for how this
maps to a review checklist.

---

## 8. Use cases / system features

### 8.1 UC-1 — Diagnose a memory leak (primary demo path)

**Actor:** on-call engineer. **Preconditions:** all five containers running; `/leak` has been
hit at least once on `target-app`.

1. Human asks *"why is target-app unhealthy?"* in the chat.
2. UI calls `POST /ask`.
3. Agent loop queries `app_leak_bytes` via `query_prometheus`, checks `get_container_status`
   and/or `get_container_logs` for target-app, observes climbing memory / repeated "OOM
   warning" log lines, and concludes a memory leak.
4. Agent calls `propose_restart(container="target-app", reason="...")`.
5. `/ask` returns `{answer, recommended_action: {type, container: "target-app", reason},
   action_id}`; this is audited as an `ask` event.
6. UI renders the diagnosis inline with an Approve/Dismiss card.
7. Human clicks **Approve restart** → `POST /approve/{action_id}` → `docker-py` restarts
   `target-app` → result audited as an `approve` event → UI shows *"Restarted target-app."*

**Postcondition:** `target-app`'s leak state is cleared (fresh process), audit log contains the
full `ask` → `approve` trail. Full sequence diagram:
[architecture.md §The core loop](architecture.md#the-core-loop-propose--approve--execute--audit).

### 8.2 UC-2 — Diagnose without recommending an action

**Actor:** on-call engineer. Human asks a question the agent can answer from metrics/logs alone
without concluding a restart is warranted (e.g., *"what's target-app's current memory
usage?"*). The agent answers via `query_prometheus` alone; no `propose_restart` call occurs;
`/ask` returns `recommended_action: null`, `action_id: null`; UI renders a plain chat message
with no action card.

### 8.3 UC-3 — Dismiss a recommendation

Same as UC-1 through step 6, but the human clicks **Dismiss**. The UI marks the message
resolved locally and never calls `/approve/{action_id}`. The `action_id` remains in
`_pending_actions` forever (no expiry mechanism exists — see [§10](#10-out-of-scope--non-goals))
but is never consumed.

### 8.4 UC-4 — Backend unreachable

Actor: anyone. `GET /audit` (polled on every UI render) fails. Vitals strip shows `down` /
`backend unreachable`; an error banner shows the exact copy from
[UI-DESIGN.md](UI-DESIGN.md#copy-write-in-the-interfaces-voice-not-a-persons). No chat
functionality is blocked, but any `/ask` call in this state will also fail and render as an
inline error message in the chat history (not a crash).

### 8.5 UC-5 — Investigation runs too long

The agent loops through all 6 rounds of `MAX_TOOL_ROUNDS` without producing a final text
response (stop_reason keeps being `tool_use`). `_run_agent` returns the fallback string
*"Investigation took too many steps — try a narrower question."* with whatever `proposed_action`
(if any) was captured along the way. This is still audited as a normal `ask` event.

---

## 9. Design constraints and rationale

Carried from [README.md](../README.md) and [architecture.md §Design decisions](architecture.md#design-decisions):

| Constraint | Rationale |
|---|---|
| One `backend` container, not split into "reasoning" and "execution" services | The safety boundary is the `/approve` gate + read-only tool set, not process isolation — splitting adds a network hop and a second deploy unit for no additional safety |
| Hand-written Claude tool-use loop, not a third-party agent framework | ~150 lines, fully owned and debuggable under a 6-hour clock; HolmesGPT was evaluated and dropped — see [holmes-gpt-reference.md](holmes-gpt-reference.md) |
| `uv`, never bare `pip` | Faster, more consistent installs across repeated container rebuilds during the build window |
| Claude via Anthropic API, not a local model | Docker Model Runner is Apple-Silicon-tuned; CPU-only and demo-flaky on Intel hosts |
| Docker Compose, not Kubernetes | minikube/kind startup alone risks 15–30 minutes on an Intel Mac — not worth it for 5 containers over 6 hours |
| JSONL flat file, not a database, for audit | Needs to be append-only, human-readable, and `tail -f`-able during a demo; a database adds a migration story for no benefit at this scale |

---

## 10. Out of scope / non-goals

Explicitly excluded, per [CLAUDE.md](../CLAUDE.md#what-this-is) and
[README.md](../README.md#what-to-build-4-pieces-nothing-else) — listed here with the gap each
would need to close before it could be added:

- **Authentication / authorization** — no login, no API keys on `/ask`/`/approve`/`/audit`.
  Needed before any multi-user or internet-exposed deployment.
- **Multi-service / multi-cluster monitoring** — the system watches exactly `target-app`; the
  vitals strip and `propose_restart` schema assume a single named container, not a fleet.
- **Kubernetes** — Compose only; no cluster-aware remediation.
- **A real database** — audit trail is `audit-log.jsonl` only; no query language, no retention
  policy, no rotation.
- **Action-proposal expiry / TTL** — `_pending_actions` entries live forever until approved;
  there's no cleanup of stale proposals from earlier questions.
- **Automated tests** — none exist yet in any of the four services (tracked as a known gap in
  [architecture.md](architecture.md#known-gaps)).
- **Alerting / paging** — Prometheus is queried on-demand by the agent; no Alertmanager, no
  proactive notification when a metric crosses a threshold (the UI's idle-state copy explicitly
  disclaims this: "Overwatch speaks up first if something breaks" is aspirational copy, not a
  wired feature, as of this read — worth flagging for future verification).
- **Tools that mutate state beyond restart** — no stop/scale/reconfigure tools; `propose_restart`
  is the only remediation shape the system knows.

---

## 11. Data requirements

### 11.1 Audit log schema (`audit-log.jsonl`)

One JSON object per line, always including `type` and `ts` (unix epoch float, set server-side
at write time):

| `type` | Additional fields |
|---|---|
| `ask` | `question` (str), `answer` (str), `action_id` (str \| null), `recommended_action` (object \| null) |
| `ask_error` | `question` (str), `error` (str) |
| `approve` | `action_id` (str), `action` (object — the original proposal), `result` (object — `{status, container, error?}`) |

No schema versioning exists; consumers (`GET /audit`, the UI's audit drawer) must tolerate
future field additions gracefully (already true — the UI renders `str(event)` per line).

### 11.2 Configuration / environment variables

| Variable | Consumed by | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `backend` | *(required, no default)* | Auth for the Anthropic SDK |
| `ANTHROPIC_MODEL` | `backend` | `claude-sonnet-5` | Model id for the agent loop |
| `PROMETHEUS_URL` | `backend` | `http://prometheus:9090` | Base URL for `query_prometheus` |
| `AUDIT_LOG_PATH` | `backend` | `/data/audit-log.jsonl` | Audit log file location |
| `TOOLSETS_CONFIG_PATH` | `backend` | `toolsets.yaml` | Which toolsets are enabled |

---

## 12. Risks

| Risk | Impact | Mitigation / status |
|---|---|---|
| `anthropic` SDK tool-use surface mismatch on a fresh install (version range `>=0.39.0,<1.0.0` unpinned) | `/ask` fails outright | Verify with a real `pip`/`uv` install before demo — flagged in [architecture.md](architecture.md#known-gaps) |
| Docker socket mount grants `backend` broad daemon access | Any compromise of `backend` (e.g., prompt injection reaching a tool call) could theoretically escalate beyond "restart target-app" if new tools are added carelessly | Keep the tool surface minimal; any new Docker-backed tool must be reviewed against [§7](#7-safety-requirements-the-human-in-the-loop-gate) before merging |
| No auth on any endpoint | Anyone on the Compose network can call `/approve/{action_id}` if they guess/observe a valid id | Acceptable for single-host demo; blocking for real deployment |
| `_pending_actions` is in-memory | A `backend` restart between proposal and approval loses all pending actions silently | Low likelihood during a short demo; would need persistence for production use |
| Judge asks a question the agent can't ground in available tools | Vague or hallucinated answer | System prompt instructs the agent to cite the specific metric/log line supporting its diagnosis, which surfaces ungrounded answers as visibly thin |

---

## 13. Acceptance criteria

Directly from [CHECKLIST.md §Demo-ready gate](CHECKLIST.md#demo-ready-gate), restated as
testable conditions:

- [ ] Hitting `/crash`, `/leak`, and `/slow` each reliably produces the described effect on
      demand, repeatably, and `/reset` returns `target-app` to baseline.
- [ ] Asking the copilot a health question after triggering a failure produces a diagnosis that
      names the correct root cause (leak / crash / slowness) without the human stating it.
- [ ] `POST /approve/{action_id}` is unreachable/ineffective without a prior matching `/ask`
      proposal, and succeeds (container observably restarts) once triggered via the UI's
      Approve button.
- [ ] `GET /audit` (and the UI's audit drawer) shows a complete `ask` → `approve` trail for a
      full demo run, in order, with no missing steps.

---

## 14. Glossary

| Term | Definition |
|---|---|
| Toolset | See [§1.5](#15-definitions-acronyms) |
| Propose → approve → execute → audit | The four-stage loop this system is built around: the agent proposes, a human approves, hand-written code executes, and every stage is logged |
| `action_id` | UUID4 minted per proposed remediation; the sole credential required to approve it |
| Vitals strip | The UI's per-service health indicator row, driven by the latest audit event, not client-side inference |
| Read-only tool | A tool whose `call()` implementation cannot reach any Docker/Compose mutation, by code inspection, not by convention alone |
