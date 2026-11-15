from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    PLANNED = "planned"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepType(str, Enum):
    ANALYZE = "analyze"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
