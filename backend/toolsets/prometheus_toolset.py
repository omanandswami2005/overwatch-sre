import requests


class PrometheusToolset:
    name = "prometheus"
    read_only = True

    def __init__(self, prometheus_url: str):
        self._url = prometheus_url

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "query_prometheus",
                "description": (
                    "Run a PromQL instant query against Prometheus. Use this to check "
                    "metrics like memory usage, request latency, or error rates."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "PromQL expression, e.g. app_leak_bytes"},
                    },
                    "required": ["query"],
                },
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name != "query_prometheus":
            raise KeyError(tool_name)
        r = requests.get(f"{self._url}/api/v1/query", params={"query": tool_input["query"]}, timeout=10)
        r.raise_for_status()
        return r.json()
