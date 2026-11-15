from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .definitions import ToolDefinition
from .exceptions import ToolExecutionError


class ToolRegistry:
    """Minimal registry for executable tool definitions."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list(self) -> List[str]:
        return sorted(self._tools.keys())

    def execute(self, name: str, **kwargs: Any) -> Any:
        definition = self._tools.get(name)
        if definition is None:
            raise ToolExecutionError(f"Tool '{name}' is not registered.")
        if definition.executor is None:
            raise ToolExecutionError(f"Tool '{name}' has no executor.")
        return definition.executor(**kwargs)
