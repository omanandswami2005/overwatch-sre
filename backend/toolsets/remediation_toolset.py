class RemediationToolset:
    """The one toolset that isn't read-only in intent — but propose_restart never
    touches the Docker daemon itself. It only records a recommendation; app.py
    surfaces that as recommended_action, and a human has to call
    POST /approve/{action_id} (a code path with no tool/model involved at all)
    before anything actually restarts.
    """

    name = "remediation"
    read_only = False

    def schemas(self) -> list[dict]:
        return [
            {
                "name": "propose_restart",
                "description": (
                    "Recommend restarting a container to remediate an issue. This does "
                    "NOT restart it — it only records a proposal that a human must "
                    "approve. Call this once you've diagnosed a problem that a restart "
                    "would plausibly fix."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string"},
                        "reason": {"type": "string", "description": "one-sentence justification"},
                    },
                    "required": ["container", "reason"],
                },
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name != "propose_restart":
            raise KeyError(tool_name)
        return {
            "status": "recorded — pending human approval",
            "container": tool_input["container"],
            "reason": tool_input["reason"],
        }
