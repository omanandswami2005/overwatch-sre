class DockerToolset:
    name = "docker"
    read_only = True

    def __init__(self, docker_client):
        self._client = docker_client

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "get_container_status",
                "description": (
                    "Get a container's current status: running/exited, health, restart "
                    "count, last exit code."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string", "description": "container name, e.g. target-app"},
                    },
                    "required": ["container"],
                },
            },
            {
                "name": "get_container_logs",
                "description": "Fetch the most recent log lines from a container.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string"},
                        "tail": {"type": "integer", "description": "number of lines, default 50"},
                    },
                    "required": ["container"],
                },
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "get_container_status":
            c = self._client.containers.get(tool_input["container"])
            c.reload()
            state = c.attrs.get("State", {})
            return {
                "name": c.name,
                "status": c.status,
                "health": state.get("Health", {}).get("Status"),
                "restart_count": c.attrs.get("RestartCount"),
                "exit_code": state.get("ExitCode"),
                "started_at": state.get("StartedAt"),
            }
        if tool_name == "get_container_logs":
            c = self._client.containers.get(tool_input["container"])
            logs = c.logs(tail=tool_input.get("tail", 50)).decode(errors="replace")
            return {"logs": logs}
        raise KeyError(tool_name)
