from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .engine import WorkflowOrchestrator
from .models import Task

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
engine = WorkflowOrchestrator()


class OrchestratorRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    context: Dict[str, Any] = {}


class OrchestratorResponse(BaseModel):
    task_id: str
    status: str
    summary: str
    steps: List[str]


@router.get("/health")
async def orchestrator_health() -> Dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}


@router.post("/run", response_model=OrchestratorResponse)
async def run_orchestration(payload: OrchestratorRequest) -> OrchestratorResponse:
    task = Task(task_id=payload.task_id, prompt=payload.prompt, context=payload.context)
    result = engine.run(task)
    return OrchestratorResponse(
        task_id=result.task_id,
        status=result.status.value,
        summary=result.summary,
        steps=[step["name"] for step in result.details.get("plan", [])],
    )
