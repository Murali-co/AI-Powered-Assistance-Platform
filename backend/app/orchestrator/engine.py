from __future__ import annotations

from typing import Any, Dict, Optional

from .capabilities import CapabilityRegistry
from .enums import TaskStatus
from .models import Task, TaskResult
from .planner import TaskPlanner


class WorkflowOrchestrator:
    """Simple orchestrator that builds plans and returns the next execution state."""

    def __init__(self, capabilities: Optional[CapabilityRegistry] = None) -> None:
        self.capabilities = capabilities or CapabilityRegistry()
        self.planner = TaskPlanner()

    def run(self, task: Task) -> TaskResult:
        plan = self.planner.build_plan(task)
        return TaskResult(
            task_id=task.task_id,
            status=TaskStatus.PLANNED,
            summary=f"Planned {len(plan.steps)} steps for task '{task.prompt}'.",
            details={"plan": [step.__dict__ for step in plan.steps]},
        )

    def list_capabilities(self) -> list[str]:
        return [capability.name for capability in self.capabilities.list()]
