from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class TaskInput(BaseModel):
    task_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    context: Dict[str, Any] = {}


class PlanStepSchema(BaseModel):
    name: str
    description: str
    status: str
    metadata: Dict[str, Any] = {}


class TaskResultSchema(BaseModel):
    task_id: str
    status: str
    summary: str
    details: Dict[str, Any] = {}
