from pathlib import Path


class RunbookToolset:
    """Read-only access to backend/runbook.md — human-authored, codified
    operational steps, distinct from the wiki (which the librarian writes
    *about* what happened; this says what to always *do*). Nothing ever
    writes to this file automatically.
    """

    name = "runbook"
    read_only = True

    def __init__(self, runbook_path: Path):
        self._path = runbook_path

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "search_runbook",
                "description": (
                    "Search the team's codified runbook for the operational steps "
                    "defined for a given failure type (e.g. 'memory leak', 'crash "
                    "loop', 'jammed queue'). Use this before deciding what action to "
                    "propose — it may specify escalation rules or a different action "
                    "than a plain restart for recurring/repeat failures."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "read_runbook",
                "description": "Read the full runbook document.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if not self._path.exists():
            return {"error": "no runbook configured"}
        text = self._path.read_text()
        if tool_name == "read_runbook":
            return {"content": text}
        if tool_name == "search_runbook":
            query = tool_input["query"].lower()
            matches = []
            current_section = ""
            for line in text.splitlines():
                if line.startswith("## "):
                    current_section = line[3:].strip()
                if query in line.lower() or any(word in current_section.lower() for word in query.split()):
                    matches.append(f"[{current_section}] {line.strip()}")
            return {"matches": matches[:40] or ["no matching section found — try read_runbook for the full doc"]}
        raise KeyError(tool_name)
