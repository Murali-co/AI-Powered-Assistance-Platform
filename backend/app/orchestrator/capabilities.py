from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Capability:
    name: str
    description: str = ""
    enabled: bool = True


class CapabilityRegistry:
    """Tracks available orchestration capabilities."""

    def __init__(self) -> None:
        self._items: Dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._items[capability.name] = capability

    def get(self, name: str) -> Optional[Capability]:
        return self._items.get(name)

    def list(self) -> List[Capability]:
        return list(self._items.values())

    def enable(self, name: str) -> None:
        capability = self._items.get(name)
        if capability is not None:
            self._items[name] = Capability(
                name=capability.name,
                description=capability.description,
                enabled=True,
            )

    def disable(self, name: str) -> None:
        capability = self._items.get(name)
        if capability is not None:
            self._items[name] = Capability(
                name=capability.name,
                description=capability.description,
                enabled=False,
            )
