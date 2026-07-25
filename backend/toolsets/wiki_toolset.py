from pathlib import Path


class WikiToolset:
    """Read-only access to the wiki the librarian agent maintains (see
    backend/librarian.py). Deliberately has no write capability — write_wiki_pages
    is not registered here or anywhere in ToolsetRegistry, so there's no config flag
    that could hand the chat agent write access by accident.
    """

    name = "wiki"
    read_only = True

    def __init__(self, wiki_dir: Path):
        self._dir = wiki_dir.resolve()

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "search_wiki",
                "description": (
                    "Search the incident/service wiki for past occurrences of a "
                    "pattern (e.g. a symptom or container name). Returns matching "
                    "lines with their source file. Use this to check whether a "
                    "current symptom has been seen before and how it was resolved."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "read_wiki_page",
                "description": "Read the full content of a wiki page, e.g. 'services/target-app.md'.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        ]

    def _safe_path(self, relative_path: str) -> Path:
        candidate = (self._dir / relative_path).resolve()
        if not candidate.is_relative_to(self._dir):
            raise ValueError(f"path escapes wiki dir: {relative_path}")
        return candidate

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "search_wiki":
            query = tool_input["query"].lower()
            matches = []
            if self._dir.exists():
                for md_file in sorted(self._dir.rglob("*.md")):
                    for i, line in enumerate(md_file.read_text().splitlines(), start=1):
                        if query in line.lower():
                            matches.append(f"{md_file.relative_to(self._dir)}:{i}: {line.strip()}")
            return {"matches": matches[:30]}
        if tool_name == "read_wiki_page":
            path = self._safe_path(tool_input["path"])
            if not path.exists():
                return {"error": f"no such wiki page: {tool_input['path']}"}
            return {"content": path.read_text()}
        raise KeyError(tool_name)
