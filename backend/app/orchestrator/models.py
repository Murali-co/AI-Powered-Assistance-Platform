from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .enums import TaskStatus
from app.db.models import Workflow as WorkflowModel, WorkflowTask as WorkflowTaskModel


@dataclass
class PlanStep:
    name: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    task_id: str
    title: str
    steps: List[PlanStep] = field(default_factory=list)


@dataclass
class Task:
    task_id: str
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
