class ToolsetRegistry:
    """Aggregates enabled Toolset modules into one Claude tool list + dispatch
    table. The agent loop in app.py only ever talks to this class — it never
    needs to know which toolset owns which tool name.
    """

    def __init__(self, toolsets):
        self.toolsets = list(toolsets)
        self._owner = {}
        for ts in self.toolsets:
            for schema in ts.schemas():
                self._owner[schema["name"]] = ts

    @property
    def schemas(self) -> list[dict]:
        return [schema for ts in self.toolsets for schema in ts.schemas()]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        ts = self._owner.get(tool_name)
        if ts is None:
            return {"error": f"no enabled toolset owns tool '{tool_name}'"}
        try:
            return ts.call(tool_name, tool_input)
        except Exception as exc:
            return {"error": str(exc)}

    def owner_name(self, tool_name: str) -> str | None:
        ts = self._owner.get(tool_name)
        return ts.name if ts else None
