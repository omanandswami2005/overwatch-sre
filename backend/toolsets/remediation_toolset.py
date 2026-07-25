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
            {
                "name": "propose_rollback",
                "description": (
                    "Recommend rolling back a container to its previous image instead of "
                    "just restarting it. Use this ONLY when a restart already happened "
                    "very recently for the same problem and it didn't help (a crash "
                    "loop) — check get_container_status's restart_count and search_wiki "
                    "for a recent prior restart of this exact container before calling "
                    "this. This does NOT execute anything — it only records a proposal "
                    "that a human must approve, same as propose_restart. Note: rollback "
                    "may not always be possible (it depends on a previous image being "
                    "available) — that's checked and reported honestly at approval time, "
                    "not here."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "container": {"type": "string"},
                        "reason": {
                            "type": "string",
                            "description": "why a restart alone isn't enough — cite the crash-loop evidence",
                        },
                    },
                    "required": ["container", "reason"],
                },
            },
        ]

    def call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name not in ("propose_restart", "propose_rollback"):
            raise KeyError(tool_name)
        return {
            "status": "recorded — pending human approval",
            "container": tool_input["container"],
            "reason": tool_input["reason"],
        }
