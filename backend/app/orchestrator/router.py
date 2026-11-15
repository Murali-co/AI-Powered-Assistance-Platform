from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from pydantic import BaseModel, Field

from .engine import WorkflowOrchestrator
from .models import Task
from . import execution

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


@router.get('/capabilities')
async def list_capabilities(user: dict = Depends(get_current_user)):
    return [{'name': name, 'description': description, 'enabled': True, 'requires_approval': approval}
            for name, (description, approval) in execution.CATALOG.items()]


@router.post('/workflows')
async def create_workflow(payload: execution.WorkflowRequest, user: dict = Depends(get_current_user)):
    workflow_id = await run_in_threadpool(execution.create, payload, user['id'])
    return await execution.advance(workflow_id, user)


class ApprovalRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)


@router.get('/workflows/{workflow_id}')
async def get_workflow(workflow_id: str, user: dict = Depends(get_current_user)):
    workflow = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not workflow or workflow['user_id'] != user['id']:
        raise HTTPException(404, 'Workflow not found.')
    return workflow


@router.post('/workflows/{workflow_id}/approve')
async def approve_workflow(workflow_id: str, payload: ApprovalRequest, user: dict = Depends(get_current_user)):
    return await execution.advance(workflow_id, user, approved_task=payload.task_id)


@router.post('/workflows/{workflow_id}/reject')
async def reject_workflow(workflow_id: str, payload: ApprovalRequest, user: dict = Depends(get_current_user)):
    return await execution.advance(workflow_id, user, approved_task=payload.task_id, reject=True)


@router.get('/workflows')
async def list_workflows(user: dict = Depends(get_current_user)):
    return await run_in_threadpool(DBManager.get_user_workflows, user['id'])


@router.get('/workflows/{workflow_id}/pending-approval')
async def pending_approval(workflow_id: str, user: dict = Depends(get_current_user)):
    workflow = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not workflow or workflow['user_id'] != user['id']:
        raise HTTPException(404, 'Workflow not found.')
    return [task for task in workflow.get('tasks', []) if task['status'] == 'AWAITING_APPROVAL']


@router.post("/run", response_model=OrchestratorResponse)
async def run_orchestration(payload: OrchestratorRequest, user: dict = Depends(get_current_user)) -> OrchestratorResponse:
    task = Task(task_id=payload.task_id, prompt=payload.prompt, context=payload.context)
    result = engine.run(task)
    return OrchestratorResponse(
        task_id=result.task_id,
        status=result.status.value,
        summary=result.summary,
        steps=[step["name"] for step in result.details.get("plan", [])],
    )
