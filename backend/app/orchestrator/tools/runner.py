from __future__ import annotations

from typing import Any, Dict

from .exceptions import ToolExecutionError, ToolPermissionError
from .permissions import PermissionManager
from .registry import ToolRegistry


class ToolRunner:
    """Executes a tool using the current permission policy."""

    def __init__(self, registry: ToolRegistry, permissions: PermissionManager | None = None) -> None:
        self.registry = registry
        self.permissions = permissions or PermissionManager()

    def run(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        definition = self.registry.get(tool_name)
        if definition is None:
            raise ToolExecutionError(f"Tool '{tool_name}' is not supported.")
        required = set(definition.permissions)
        if not self.permissions.can_run(tool_name, required):
            raise ToolPermissionError(f"Missing permissions to execute '{tool_name}'.")
        result = self.registry.execute(tool_name, **kwargs)
        return {"tool": tool_name, "result": result}
