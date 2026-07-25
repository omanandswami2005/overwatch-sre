"""The watcher (speaks first) and the librarian (documents afterward) —
condensed from docs/architecture.md's "Proactive watching" and "Two agents,
one write boundary" sections. Both are backend-triggered policy, not
something the chat agent decides to do via a tool call.
"""

_CARDS = [
    (
        "the watcher",
        "backend/watcher.py",
        "A background thread runs two cheap, deterministic checks every 30s per "
        "container — no LLM call unless one trips. Only then does it run the exact "
        "same investigation a typed question would, tagged source: \"watcher\" in "
        "the audit log so you can tell \"the copilot noticed\" from \"someone asked.\"",
    ),
    (
        "the librarian",
        "backend/librarian.py",
        "A second, isolated agent whose only tool is write_wiki_pages — it can't "
        "read Prometheus or Docker, and the chat agent can't write. Triggered "
        "automatically after an approved restart, it archives the incident into a "
        "self-updating wiki the chat agent later cites by ID.",
    ),
]


def html() -> str:
    cards = "".join(
        f"""<div class="feature-card">
        <span class="feature-port">{path}</span>
        <div class="feature-name">{name}</div>
        <div class="feature-desc">{desc}</div>
        </div>"""
        for name, path, desc in _CARDS
    )
    return (
        '<div><div class="section-label">it also watches and remembers</div>'
        f'<div class="feature-grid">{cards}</div></div>'
    )
