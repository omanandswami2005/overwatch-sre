# HolmesGPT reference (historical — safe to delete)

**Status:** this project no longer uses HolmesGPT. The backend was rewritten to call the
Anthropic API directly with a small custom tool-use loop instead of shelling out to the
`holmes` CLI. This file exists only as a record of what HolmesGPT was and how this repo used
to integrate it, in case that context is useful later. **Delete this file whenever it's no
longer needed** — nothing else in the repo links to or depends on it.

## What HolmesGPT is

[HolmesGPT](https://github.com/robusta-dev/holmesgpt) is an open-source AI agent for on-call/SRE
root-cause investigation, maintained by Robusta and hosted as a CNCF Sandbox project. Given a
natural-language question, it reasons over an LLM with a set of "toolsets" — pluggable
integrations into data sources — to investigate and answer.

Key features (as understood at the time this repo used it):

- **`holmes ask "<question>"`** — CLI entry point for one-off investigation questions.
- **Toolsets** — config-driven integrations it can call during investigation, including (among
  others) `docker/core` (docker ps/logs/inspect), `prometheus/metrics` (PromQL queries),
  Kubernetes, Grafana, and various cloud-provider integrations. Enabled/disabled per-toolset via
  a config file (this repo's former `backend/holmes-config.yaml`).
  set:
  ```yaml
  toolsets:
    docker/core:
      enabled: true
    prometheus/metrics:
      enabled: true
      config:
        prometheus_url: "http://prometheus:9090"
  ```
- **Read-only by design** — the toolsets HolmesGPT ships are investigation tools (list, get,
  query); it does not have a built-in "restart this container" or other mutating action. Any
  remediation/action step has to be built on top of it, which is what this repo's
  propose→approve→execute→audit loop was for.
- **LLM-agnostic** — supports Anthropic, OpenAI, and other providers as the reasoning backend;
  this repo pointed it at Claude via `ANTHROPIC_API_KEY`.
- **Distributed as a Docker image** (`robustadev/holmes:<version>`) as well as a pip-installable
  CLI/library.

## How this repo used to integrate it

- `backend/Dockerfile` extended `FROM robustadev/holmes:0.36.0`, added the `docker` CLI binary
  (`apk add --no-cache docker-cli`) because the base image didn't ship it and the `docker/core`
  toolset shells out to it, then layered `fastapi`/`uvicorn` on top via `uv`.
- `backend/holmes-config.yaml` was mounted to `/root/.holmes/config.yaml` inside the container,
  enabling only `docker/core` and `prometheus/metrics` (no write/mutating toolsets), pointing
  `prometheus_url` at the in-compose Prometheus service.
- `backend/app.py`'s `POST /ask` handler ran `subprocess.run(["python", "/app/holmes_cli.py",
  "ask", question], ...)`, parsed stdout as the diagnosis text, and used a keyword regex
  (`RESTART_TRIGGERS`) over that text to decide whether to surface a recommended restart action.

## Why this repo stopped using it

Two reasons drove the pivot to a custom Claude tool-use agent (see
[architecture.md](architecture.md#design-decisions) for the current rationale):

1. **Unverified integration risk under time pressure.** The exact `holmes ask` CLI invocation
   and the `holmes-config.yaml` schema were never confirmed against the actual installed
   version before code was written (both were flagged in-code as unverified) — a real risk for
   a 6.5-hour build with no slack to debug a third-party CLI's exact flags.
2. **Ownership of the "agent" claim.** The hackathon problem statement asks for "an LLM-powered
   agent wired to live metrics/logs/traces" — wrapping an existing agent's CLI is a legitimate
   integration, but a small hand-written Claude tool-use loop (a handful of read-only tools plus
   a `propose_restart` tool, run through the Anthropic Messages API directly) is both simpler to
   build/debug than fighting an unfamiliar external binary, and unambiguously "the agent we
   built" for demo/judging purposes.

Prometheus remains in the stack either way and already satisfies a "use a CNCF project" angle on
its own (Prometheus is CNCF graduated), independent of whether HolmesGPT — a CNCF Sandbox project
— is used.
