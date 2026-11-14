import logging
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from typing import List, Dict, Any

from app.auth.utils import get_current_user
from app.orchestrator.schemas import WorkflowSchema, WorkflowCreateRequest
from app.orchestrator.enums import WorkflowState
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.capabilities import CapabilityRegistry
from app.orchestrator.tools.registry import ToolRegistry
from app.orchestrator.tools.runner import ToolRunner
from app.orchestrator.tools.parser import LLMToolParser
from app.orchestrator.tools.schemas import ToolDefinitionSchema, ToolExecutionRequest, ToolExecutionResult
from app.orchestrator.tools.exceptions import (
    UnknownToolError,
    UnauthorizedToolError,
    InvalidToolArgumentsError,
    ToolExecutionTimeoutError,
    ToolExecutionError,
    MalformedToolRequestError
)
from app.llm.ollama_client import OllamaClient
from app.auth.models import DBManager
from app.utils.limiter import limiter
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

@router.get("/capabilities", response_model=List[Dict[str, Any]])
async def list_capabilities(current_user: dict = Depends(get_current_user)):
    """List all safe, approved capabilities available to the orchestrator."""
    caps = CapabilityRegistry.get_all()
    return [
        {"name": c["name"], "description": c["description"], "risk_tier": c["risk_tier"]}
        for c in caps.values()
    ]

# ==================== TOOL FRAMEWORK ENDPOINTS ====================
@router.get("/tools", response_model=List[ToolDefinitionSchema])
async def list_tools(current_user: dict = Depends(get_current_user)):
    """List all registered local tools with schemas, permissions, and status."""
    tools = ToolRegistry.get_all_tools()
    return [t.to_schema() for t in tools.values()]

@router.post("/tools/execute", response_model=ToolExecutionResult)
@limiter.limit("20/minute")
async def execute_tool_directly(
    request: Request,
    tool_req: ToolExecutionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute a registered tool directly with schema validation and permission enforcement."""
    try:
        result = await ToolRunner.execute_tool(user_dict=current_user, request=tool_req)
        return result
    except UnknownToolError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedToolError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidToolArgumentsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ToolExecutionTimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Tool execution timed out.")
    except ToolExecutionError as e:
        logger.exception("Tool execution error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tool execution encountered an internal error.")

@router.post("/tools/invoke-llm", response_model=Dict[str, Any])
@limiter.limit("20/minute")
async def invoke_llm_tool(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Prompt the local LLM agent to select and execute the optimal tool for a task."""
    user_prompt = payload.get("prompt", "").strip()
    if not user_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt cannot be empty.")

    tools = ToolRegistry.get_enabled_tools()
    tool_descriptions = "\n".join([
        f"- '{t.name}': {t.description} (Inputs: {(t.input_schema_class.model_json_schema() if hasattr(t.input_schema_class, 'model_json_schema') else t.input_schema_class.schema()).get('properties', {})})"
        for t in tools.values()
    ])

    system_prompt = (
        "You are an AI Agent with access to local tool capabilities. "
        "Select the single best tool for the user task and format your response ONLY in valid JSON.\n"
        "Example JSON format:\n"
        "{\n"
        '  "tool_name": "search_jobs",\n'
        '  "arguments": {"search_term": "Python Engineer"}\n'
        "}\n"
        "Return ONLY JSON."
    )

    llm_prompt = f"""
Available Local Tools:
{tool_descriptions}

User Task:
"{user_prompt}"

Select tool and return JSON:
"""
    try:
        raw_output = await OllamaClient.generate(prompt=llm_prompt, system=system_prompt, format="json")
        parsed_payload = LLMToolParser.parse_tool_call(raw_output)

        tool_request = ToolExecutionRequest(
            tool_name=parsed_payload.tool_name,
            arguments=parsed_payload.arguments
        )

        exec_result = await ToolRunner.execute_tool(user_dict=current_user, request=tool_request)
        return {
            "llm_selected_tool": parsed_payload.tool_name,
            "arguments": parsed_payload.arguments,
            "result": getattr(exec_result, "model_dump", getattr(exec_result, "dict", None))()
        }
    except MalformedToolRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UnknownToolError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnauthorizedToolError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except InvalidToolArgumentsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ToolExecutionTimeoutError as e:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Tool execution timed out.")
    except ToolExecutionError as e:
        logger.exception("Tool execution error: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tool execution encountered an internal error.")

# ==================== WORKFLOW ENDPOINTS ====================
@router.post("/workflows", response_model=WorkflowSchema, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_and_run_workflow(
    request: Request,
    workflow_req: WorkflowCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create and execute an Orchestrator workflow for a given user goal."""
    if not workflow_req.goal.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal cannot be empty."
        )

    workflow = await OrchestratorEngine.run_workflow(
        user_id=current_user["id"],
        request=workflow_req
    )
    return workflow

@router.get("/workflows", response_model=List[WorkflowSchema])
async def list_user_workflows(current_user: dict = Depends(get_current_user)):
    """Retrieve all orchestrator workflows created by the current user."""
    workflows = await run_in_threadpool(DBManager.get_user_workflows, current_user["id"])
    return [WorkflowSchema(**wf) for wf in workflows]

@router.get("/workflows/{workflow_id}", response_model=WorkflowSchema)
async def get_workflow_details(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed workflow status, error info, and task execution breakdown."""
    wf_dict = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )
    return WorkflowSchema(**wf_dict)

@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowSchema)
async def cancel_workflow_execution(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel an active or pending orchestrator workflow."""
    wf_dict = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )

    current_status = wf_dict.get("status")
    if current_status in [WorkflowState.COMPLETED.value, WorkflowState.FAILED.value, WorkflowState.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow is already in terminal state '{current_status}'."
        )

    OrchestratorEngine.cancel_workflow(workflow_id)
    await run_in_threadpool(DBManager.finish_workflow, workflow_id, WorkflowState.CANCELLED.value, error="Workflow cancelled by user.")

    updated_wf = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not updated_wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowSchema(**updated_wf)

@router.get("/workflows/{workflow_id}/pending-approval", response_model=List[Dict[str, Any]])
async def get_pending_approvals(
    workflow_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve all tasks in a workflow that are currently awaiting human approval."""
    wf_dict = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )

    tasks = wf_dict.get("tasks", [])
    pending = []
    for t in tasks:
        t_dict = t if isinstance(t, dict) else t.model_dump()
        if t_dict.get("status") in ["AWAITING_APPROVAL", WorkflowState.AWAITING_APPROVAL.value]:
            task_type = t_dict.get("task_type", "")
            risk_tier = CapabilityRegistry.get_risk_tier(task_type) if CapabilityRegistry.is_valid_capability(task_type) else "unknown"
            input_data = t_dict.get("input", {})
            company = input_data.get("company", "Target Company")
            title = input_data.get("title", input_data.get("target_role", "Target Position"))

            pending.append({
                "task_id": t_dict.get("task_id"),
                "task_type": task_type,
                "description": t_dict.get("description"),
                "risk_tier": risk_tier,
                "status": "AWAITING_APPROVAL",
                "input": input_data,
                "summary": f"Submit application to {company} for {title} using your tailored resume"
            })
    return pending

@router.post("/workflows/{workflow_id}/approve", response_model=WorkflowSchema)
async def approve_pending_task(
    workflow_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Approve a pending external action task and resume workflow execution."""
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id is required."
        )

    wf_dict = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )

    tasks = wf_dict.get("tasks", [])
    target_task = None
    for t in tasks:
        t_dict = t if isinstance(t, dict) else t.model_dump()
        if t_dict.get("task_id") == task_id:
            target_task = t_dict
            break

    if not target_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found in workflow."
        )

    if target_task.get("status") not in ["AWAITING_APPROVAL", WorkflowState.AWAITING_APPROVAL.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_id}' is in status '{target_task.get('status')}', not AWAITING_APPROVAL."
        )

    # Log audit event
    await run_in_threadpool(
        DBManager.log_auth_event,
        user_id=current_user["id"],
        event_type="orchestrator_approval_approved",
        ip_address="127.0.0.1",
        user_agent="Client",
        detail=f"User '{current_user['email']}' approved task '{task_id}' ({target_task.get('task_type')}) in workflow '{workflow_id}'"
    )

    # Resume workflow execution
    resumed_wf = await OrchestratorEngine.resume_workflow(
        user_id=current_user["id"],
        workflow_id=workflow_id,
        approved_task_id=task_id
    )
    return resumed_wf

@router.post("/workflows/{workflow_id}/reject", response_model=WorkflowSchema)
async def reject_pending_task(
    workflow_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Reject a pending external action task and cancel workflow execution."""
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id is required."
        )

    wf_dict = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not wf_dict or wf_dict.get("user_id") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found."
        )

    tasks = wf_dict.get("tasks", [])
    target_task = None
    for t in tasks:
        t_dict = t if isinstance(t, dict) else t.model_dump()
        if t_dict.get("task_id") == task_id:
            target_task = t_dict
            break

    if not target_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found in workflow."
        )

    # Log audit event
    await run_in_threadpool(
        DBManager.log_auth_event,
        user_id=current_user["id"],
        event_type="orchestrator_approval_rejected",
        ip_address="127.0.0.1",
        user_agent="Client",
        detail=f"User '{current_user['email']}' rejected task '{task_id}' ({target_task.get('task_type')}) in workflow '{workflow_id}'"
    )

    # Mark task and workflow as CANCELLED
    await run_in_threadpool(DBManager.update_task_status, workflow_id, task_id, "CANCELLED")
    await run_in_threadpool(DBManager.finish_workflow, workflow_id, WorkflowState.CANCELLED.value, error=f"Task '{task_id}' rejected by user.")

    updated_wf = await run_in_threadpool(DBManager.get_workflow, workflow_id)
    if not updated_wf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowSchema(**updated_wf)
