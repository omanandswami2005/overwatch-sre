from typing import Protocol, runtime_checkable


@runtime_checkable
class Toolset(Protocol):
    """Structural interface every toolset module implements — no base class to
    inherit, just match this shape. Mirrors HolmesGPT's toolset concept (a
    self-contained, config-enable-able unit of tool schemas + execution), but
    ours: add a capability by writing a module matching this protocol,
    registering it in app.py's _build_registry(), and flipping it on in
    toolsets.yaml. Nothing else in the agent loop changes.
    """

    name: str
    read_only: bool

    def schemas(self) -> list[dict]: ...

    def call(self, tool_name: str, tool_input: dict) -> dict: ...
