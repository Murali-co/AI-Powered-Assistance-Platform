from __future__ import annotations

from typing import Iterable, Set


class PermissionManager:
    """Stores the permitted tool actions for a session or actor."""

    def __init__(self, allowed: Iterable[str] | None = None) -> None:
        self.allowed: Set[str] = set(allowed or [])

    def can_run(self, tool_name: str, required: Iterable[str] | None = None) -> bool:
        required_set = set(required or [])
        if not required_set:
            return True
        return required_set.issubset(self.allowed)
