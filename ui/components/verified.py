"""What's actually been verified end-to-end — pulled straight from
docs/CHECKLIST.md's demo-ready gate (all four items are checked there).
Real completed-checklist items, not vanity claims.
"""

_CHECKS = [
    "Failure injection reliably reproduces on demand — /leak, /slow, /crash all tested.",
    "The copilot names the root cause unprompted for all three: memory leak "
    "(cites app_leak_bytes + OOM log lines), injected latency (correctly declines "
    "to recommend a restart since it's self-resolving), crash (cites exit code + "
    "FATAL log line).",
    "The restart is blocked until Approve is clicked, and works after — verified "
    "for the leak and crash scenarios.",
    "audit-log.jsonl shows the full ask/approve trail, and the watcher + librarian "
    "loop is verified too: a follow-up question about a resolved incident correctly "
    "cites the prior wiki entry by ID.",
]

_CAPTION = (
    "Known gaps: no automated tests yet, no CI — this has been verified manually, "
    "locally, not re-run automatically on every change. See docs/architecture.md "
    "→ Known gaps for the full list."
)


def html() -> str:
    items = "".join(
        f'<div class="check-item"><span class="check-mark">&#10003;</span><span>{c}</span></div>'
        for c in _CHECKS
    )
    return (
        '<div><div class="section-label">verified, not just built</div>'
        f'<div class="verified-panel">{items}<div class="verified-caption">{_CAPTION}</div></div></div>'
    )
