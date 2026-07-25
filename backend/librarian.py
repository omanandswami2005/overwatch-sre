import os
from pathlib import Path

import anthropic

WIKI_DIR = Path(os.environ.get("WIKI_DIR", "/data/wiki")).resolve()
WIKI_DIR.mkdir(parents=True, exist_ok=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
anthropic_client = anthropic.Anthropic()

LIBRARIAN_SYSTEM_PROMPT = (
    "You are the Overwatch archivist. You do not talk to users — you maintain a small "
    "wiki of interconnected markdown pages documenting this system's services and past "
    "incidents. You are given one resolved incident (a diagnosis that led to an "
    "approved, executed restart) plus whatever wiki pages already exist for that "
    "service. Update or create exactly these pages via write_wiki_pages, in one call: "
    "index.md (top-level links to every service page and the most recent incidents, "
    "newest first), services/<container>.md (a short overview plus an 'Observed "
    "failure signatures' section — append this incident's pattern if new, don't repeat "
    "if a near-identical one is already listed), and incidents/<action_id>.md (the "
    "question asked, the diagnosis, the evidence cited, the action taken, and the "
    "outcome, with a link back to the service page). Always write the FULL content of "
    "every page you touch — you are overwriting the file, not diffing it. Keep prose "
    "tight; this is a reference wiki, not a report."
)

WRITE_WIKI_PAGES_TOOL = {
    "name": "write_wiki_pages",
    "description": (
        "Write or overwrite one or more wiki pages. Each path is relative to the wiki "
        "root, e.g. 'index.md', 'services/target-app.md', 'incidents/<action_id>.md'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string", "description": "full markdown content"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        "required": ["pages"],
    },
}


def _safe_wiki_path(relative_path: str) -> Path:
    """Resolve a librarian-supplied path and refuse anything that would escape
    WIKI_DIR (e.g. '../../etc/passwd') — the path comes from LLM output, so it's
    untrusted input, not a trusted internal value.
    """
    candidate = (WIKI_DIR / relative_path).resolve()
    if not candidate.is_relative_to(WIKI_DIR):
        raise ValueError(f"refusing to write outside wiki dir: {relative_path}")
    return candidate


def _read_existing_page(relative_path: str) -> str:
    path = WIKI_DIR / relative_path
    if path.exists():
        return path.read_text()
    return "(page does not exist yet)"


def run_librarian(incident: dict) -> list[str]:
    """Best-effort: called after a human-approved restart succeeds. Returns the list
    of wiki paths written, or raises — callers should treat failures as non-fatal to
    the actual incident response.
    """
    container = incident["container"]
    context = (
        f"Resolved incident for service '{container}':\n\n"
        f"Question asked: {incident['question']}\n"
        f"Diagnosis: {incident['answer']}\n"
        f"Proposed action: restart {container} — {incident['reason']}\n"
        f"Approval result: {incident['result']}\n"
        f"Timestamp: {incident['ts']}\n"
        f"action_id: {incident['action_id']}\n\n"
        f"Existing services/{container}.md:\n{_read_existing_page(f'services/{container}.md')}\n\n"
        f"Existing index.md:\n{_read_existing_page('index.md')}"
    )

    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=LIBRARIAN_SYSTEM_PROMPT,
        tools=[WRITE_WIKI_PAGES_TOOL],
        tool_choice={"type": "tool", "name": "write_wiki_pages"},
        messages=[{"role": "user", "content": context}],
    )

    written = []
    for block in response.content:
        if block.type != "tool_use" or block.name != "write_wiki_pages":
            continue
        for page in block.input["pages"]:
            target = _safe_wiki_path(page["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(page["content"])
            written.append(page["path"])
    return written
