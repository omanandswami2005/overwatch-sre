# Overwatch runbook

Codified operational steps — human-authored, deterministic, not the LLM's general
knowledge. Distinct from `wiki/` (which the librarian agent writes *about* what
actually happened): this file says what the on-call team has decided to *always*
do for a given failure class, before the agent starts reasoning freely. Read-only
to the chat agent via `search_runbook`/`read_runbook` (`RunbookToolset`) — nothing
ever writes to this file automatically; it's edited by a human like any other
source file.

## target-app: memory leak (OOM warning / app_leak_bytes climbing)

1. Confirm via `query_prometheus("app_leak_bytes")` — rising, not a single spike.
2. Check `get_container_logs` for repeated `OOM warning: leaked chunk added` lines.
3. Check `search_wiki` for prior occurrences of this exact pattern on this container.
4. If this is a first-time or infrequent occurrence: `propose_restart` is the
   correct, sufficient action. State the evidence (metric value + log lines) in
   the reason.
5. If the wiki/audit history shows this is the 2nd+ occurrence within a short
   window (same container, same symptom): still `propose_restart` (only real
   fix available), but explicitly say in the answer that this is recurring and
   should be escalated to the service owner as a code-level bug, not treated as
   a one-off. A restart is a mitigation here, not a fix.

## target-app: crash (process exit, FATAL log line)

1. Check `get_container_status` — `exit_code`, `restart_count`.
2. Check `get_container_logs` for the `FATAL` line preceding the exit.
3. If `restart_count` is low and this is the first exit seen for this incident:
   `propose_restart`.
4. If the container has already been restarted for this same crash pattern very
   recently (i.e. this is a crash immediately after a prior approved restart —
   a crash loop): do **not** just propose another identical restart. Call
   `propose_rollback` instead if available, and say explicitly that a repeat
   restart is unlikely to help since it already failed once.

## worker-service: jammed queue (worker_jammed=1)

1. Confirm via `query_prometheus('worker_jammed{job="worker-service"}')` == 1.
2. Check `get_container_logs` for the `FATAL: worker queue processing jammed`
   line and rising `worker_queue_depth`.
3. `propose_restart` — resets the consumer loop. Note in the reason that this is
   a stuck-state signature, not a resource leak, so no growth trend is expected
   in metrics beforehand — a sudden jump to `jammed=1` is itself the signal.

## General escalation rule (applies across all of the above)

Before proposing a restart, always check `search_wiki` for this container's
prior incidents. If this exact failure type has occurred **2 or more times**
for the same container within recent history, the answer must say so explicitly
and recommend escalation (e.g. "this is the 3rd occurrence of this pattern —
recommend filing a ticket / escalating to the service owner, a restart is not a
long-term fix") rather than presenting it as a fresh, isolated incident.
