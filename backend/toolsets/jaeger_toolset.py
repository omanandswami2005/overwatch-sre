import requests


class JaegerToolset:
    name = "jaeger"
    read_only = True

    def __init__(self, jaeger_query_url: str):
        self._url = jaeger_query_url

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "query_traces",
                "description": (
                    "Fetch recent request traces for a service from Jaeger. Use this to "
                    "see which specific endpoint/operation is slow and by how much, or to "
                    "confirm requests are completing normally. Each trace is a request; "
                    "each span within it is a step in handling that request."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "service name, e.g. target-app"},
                        "lookback_minutes": {"type": "integer", "description": "default 15"},
                        "limit": {"type": "integer", "description": "max traces to return, default 10"},
                    },
                    "required": ["service"],
                },
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name != "query_traces":
            raise KeyError(tool_name)

        r = requests.get(
            f"{self._url}/api/traces",
            params={
                "service": tool_input["service"],
                "lookback": f"{tool_input.get('lookback_minutes', 15)}m",
                "limit": tool_input.get("limit", 10),
            },
            timeout=10,
        )
        r.raise_for_status()
        traces = r.json().get("data", [])

        summaries = []
        for trace in traces:
            spans = trace.get("spans", [])
            if not spans:
                continue
            root = min(spans, key=lambda s: s.get("startTime", 0))
            summaries.append(
                {
                    "trace_id": trace.get("traceID"),
                    "root_operation": root.get("operationName"),
                    "duration_ms": round(root.get("duration", 0) / 1000, 2),
                    "span_count": len(spans),
                    "spans": [
                        {"operation": s.get("operationName"), "duration_ms": round(s.get("duration", 0) / 1000, 2)}
                        for s in spans
                    ],
                }
            )
        return {"traces": summaries, "lookback_minutes": tool_input.get("lookback_minutes", 15)}
