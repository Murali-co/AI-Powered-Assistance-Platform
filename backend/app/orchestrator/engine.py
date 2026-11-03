import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
import json

from app.orchestrator.enums import WorkflowState, TaskState
from app.orchestrator.schemas import WorkflowSchema, TaskSchema, PlanSchema, WorkflowCreateRequest
from app.orchestrator.planner import GoalPlanner
from app.orchestrator.capabilities import CapabilityRegistry
from app.auth.models import DBManager

class OrchestratorEngine:
    """
    Central Agent Orchestrator Engine managing goal planning, task capability execution,
    state transitions, retries, timeouts, dependency resolutions, and cancellation.
    """
    _cancelled_workflows: Set[str] = set()

    @classmethod
    def cancel_workflow(cls, workflow_id: str):
        """Mark a workflow as cancelled in the runtime registry."""
        cls._cancelled_workflows.add(workflow_id)

    @classmethod
    def is_cancelled(cls, workflow_id: str) -> bool:
        if workflow_id in cls._cancelled_workflows:
            return True
        # Also check DB status
        wf = DBManager.get_workflow(workflow_id)
        if wf and wf.get("status") == WorkflowState.CANCELLED.value:
            return True
        return False

    @classmethod
    async def run_workflow(
        cls,
        user_id: int,
        request: WorkflowCreateRequest
    ) -> WorkflowSchema:
        workflow_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')

        # 1. Initialize PENDING workflow record
        workflow = WorkflowSchema(
            workflow_id=workflow_id,
            user_id=user_id,
            goal=request.goal,
            status=WorkflowState.PENDING,
            tasks=[],
            created_at=now_str
        )
        dump_fn = getattr(workflow, "model_dump", getattr(workflow, "dict", None))
        DBManager.save_workflow(dump_fn())

        start_time = asyncio.get_event_loop().time()
        timeout_limit = request.execution_timeout if request.execution_timeout is not None else 120.0
        retries_limit = request.max_retries if request.max_retries is not None else 2
        steps_limit = request.max_steps if request.max_steps is not None else 10

        try:
            # 2. State: PLANNING
            if cls.is_cancelled(workflow_id):
                return cls._mark_workflow_cancelled(workflow_id)

            cls._update_workflow_status(workflow_id, WorkflowState.PLANNING)
            plan = await GoalPlanner.create_plan(goal=request.goal, max_steps=steps_limit)

            # Create initial tasks from plan
            tasks: List[TaskSchema] = []
            for t_spec in plan.tasks:
                task = TaskSchema(
                    task_id=t_spec.task_id,
                    workflow_id=workflow_id,
                    task_type=t_spec.task_type,
                    description=t_spec.description,
                    status=TaskState.PENDING,
                    input=t_spec.input,
                    dependencies=t_spec.dependencies,
                    created_at=now_str
                )
                tasks.append(task)

            workflow.tasks = tasks
            DBManager.update_workflow_tasks(
                workflow_id, 
                [getattr(t, "model_dump", getattr(t, "dict", None))() for t in tasks]
            )

            # 3. State: RUNNING
            cls._update_workflow_status(workflow_id, WorkflowState.RUNNING)

            completed_task_outputs: Dict[str, Dict[str, Any]] = {}
            pending_task_map = {t.task_id: t for t in tasks}

            while pending_task_map:
                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_limit:
                    return cls._mark_workflow_failed(
                        workflow_id,
                        f"Workflow execution timed out after {timeout_limit:.1f}s."
                    )

                # Check cancellation
                if cls.is_cancelled(workflow_id):
                    return cls._mark_workflow_cancelled(workflow_id)

                # Find tasks whose dependencies are fully satisfied
                ready_tasks = [
                    task for task in pending_task_map.values()
                    if task.status == TaskState.PENDING and
                    all(dep_id in completed_task_outputs for dep_id in task.dependencies)
                ]

                if not ready_tasks:
                    # Check if any task is awaiting approval
                    awaiting_tasks = [t for t in pending_task_map.values() if t.status == TaskState.AWAITING_APPROVAL]
                    if awaiting_tasks:
                        cls._update_workflow_status(workflow_id, WorkflowState.AWAITING_APPROVAL)
                        return cls._get_workflow_schema(workflow_id, WorkflowState.AWAITING_APPROVAL)

                    # Circular dependency or missing task
                    unresolved = [t.task_id for t in pending_task_map.values() if t.status in [TaskState.PENDING, TaskState.AWAITING_APPROVAL]]
                    return cls._mark_workflow_failed(
                        workflow_id,
                        f"Workflow blocked by unsatisfied task dependencies: {unresolved}"
                    )

                for task in ready_tasks:
                    # Execute ready task
                    if cls.is_cancelled(workflow_id):
                        return cls._mark_workflow_cancelled(workflow_id)

                    # Check capability risk tier
                    risk_tier = CapabilityRegistry.get_risk_tier(task.task_type)
                    if risk_tier == "external_action":
                        user_info = DBManager.get_user_by_id(user_id) or {}
                        auto_approve = user_info.get("auto_approve_external_actions", False)
                        if auto_approve:
                            DBManager.log_auth_event(
                                user_id=user_id,
                                event_type="orchestrator_approval_auto_approved",
                                ip_address="127.0.0.1",
                                user_agent="OrchestratorEngine",
                                detail=f"Auto-approved task '{task.task_id}' ({task.task_type}) for workflow '{workflow_id}'"
                            )
                        else:
                            # Pause execution and transition to AWAITING_APPROVAL
                            cls._update_task_status(workflow_id, task.task_id, TaskState.AWAITING_APPROVAL)
                            cls._update_workflow_status(workflow_id, WorkflowState.AWAITING_APPROVAL)
                            DBManager.log_auth_event(
                                user_id=user_id,
                                event_type="orchestrator_approval_submitted",
                                ip_address="127.0.0.1",
                                user_agent="OrchestratorEngine",
                                detail=f"Task '{task.task_id}' ({task.task_type}) submitted for human approval in workflow '{workflow_id}'"
                            )
                            return cls._get_workflow_schema(workflow_id, WorkflowState.AWAITING_APPROVAL)

                    # Inject outputs from dependency tasks into task input if relevant
                    merged_input = cls._merge_dependency_inputs(task.input, task.dependencies, completed_task_outputs)

                    task_success = False
                    task_output = None
                    last_error = None

                    # Retry loop
                    for attempt in range(retries_limit + 1):
                        # Re-check cancellation before each attempt
                        if cls.is_cancelled(workflow_id):
                            return cls._mark_workflow_cancelled(workflow_id)

                        cls._update_task_status(workflow_id, task.task_id, TaskState.RUNNING)

                        try:
                            # Execute task capability
                            task_output = await asyncio.wait_for(
                                CapabilityRegistry.execute(
                                    name=task.task_type,
                                    user_id=user_id,
                                    input_data=merged_input
                                ),
                                timeout=min(30.0, timeout_limit)
                            )
                            task_success = True
                            break
                        except asyncio.TimeoutError:
                            last_error = "Task execution timed out."
                            print(f"[OrchestratorEngine] Task '{task.task_id}' attempt {attempt + 1} timed out.")
                            if attempt < retries_limit:
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            last_error = str(e) or type(e).__name__
                            print(f"[OrchestratorEngine] Task '{task.task_id}' attempt {attempt + 1} failed: {e}")
                            if attempt < retries_limit:
                                await asyncio.sleep(0.5)

                    if task_success:
                        # Task completed successfully
                        completed_task_outputs[task.task_id] = task_output or {}
                        cls._update_task_completed(workflow_id, task.task_id, task_output)
                        pending_task_map.pop(task.task_id)
                    else:
                        # Task failed after all retries
                        cls._update_task_failed(workflow_id, task.task_id, last_error or "Unknown error")
                        return cls._mark_workflow_failed(
                            workflow_id,
                            f"Task '{task.task_id}' ({task.task_type}) failed: {last_error}"
                        )

            # 4. State: COMPLETED
            if cls.is_cancelled(workflow_id):
                return cls._mark_workflow_cancelled(workflow_id)

            return cls._mark_workflow_completed(workflow_id)

        except Exception as e:
            print(f"[OrchestratorEngine] Workflow '{workflow_id}' failed: {e}")
            return cls._mark_workflow_failed(workflow_id, f"Orchestrator exception: {str(e)}")

    @classmethod
    async def resume_workflow(
        cls,
        user_id: int,
        workflow_id: str,
        approved_task_id: str,
        execution_timeout: float = 60.0,
        max_retries: int = 1
    ) -> WorkflowSchema:
        """Resume a workflow after a task has been approved."""
        wf_dict = DBManager.get_workflow(workflow_id)
        if not wf_dict:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        # Update approved task status to PENDING so it can be picked up
        cls._update_task_status(workflow_id, approved_task_id, TaskState.PENDING)
        cls._update_workflow_status(workflow_id, WorkflowState.RUNNING)

        # Re-fetch tasks
        tasks_raw = wf_dict.get("tasks", [])
        tasks: List[TaskSchema] = [TaskSchema(**t) if isinstance(t, dict) else t for t in tasks_raw]

        # Populate completed task outputs
        completed_task_outputs: Dict[str, Dict[str, Any]] = {}
        pending_task_map: Dict[str, TaskSchema] = {}

        for t in tasks:
            if t.task_id == approved_task_id:
                t.status = TaskState.PENDING
            if t.status == TaskState.COMPLETED:
                completed_task_outputs[t.task_id] = t.output or {}
            else:
                pending_task_map[t.task_id] = t

        start_time = asyncio.get_event_loop().time()

        while pending_task_map:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > execution_timeout:
                return cls._mark_workflow_failed(workflow_id, f"Workflow execution timed out after {execution_timeout:.1f}s.")

            if cls.is_cancelled(workflow_id):
                return cls._mark_workflow_cancelled(workflow_id)

            ready_tasks = [
                task for task in pending_task_map.values()
                if task.status == TaskState.PENDING and
                all(dep_id in completed_task_outputs for dep_id in task.dependencies)
            ]

            if not ready_tasks:
                awaiting_tasks = [t for t in pending_task_map.values() if t.status == TaskState.AWAITING_APPROVAL]
                if awaiting_tasks:
                    cls._update_workflow_status(workflow_id, WorkflowState.AWAITING_APPROVAL)
                    return cls._get_workflow_schema(workflow_id, WorkflowState.AWAITING_APPROVAL)
                unresolved = [t.task_id for t in pending_task_map.values() if t.status in [TaskState.PENDING, TaskState.AWAITING_APPROVAL]]
                return cls._mark_workflow_failed(workflow_id, f"Workflow blocked by unsatisfied task dependencies: {unresolved}")

            for task in ready_tasks:
                if cls.is_cancelled(workflow_id):
                    return cls._mark_workflow_cancelled(workflow_id)

                risk_tier = CapabilityRegistry.get_risk_tier(task.task_type)
                # If this task was just approved, we skip re-asking approval for it
                if risk_tier == "external_action" and task.task_id != approved_task_id:
                    user_info = DBManager.get_user_by_id(user_id) or {}
                    auto_approve = user_info.get("auto_approve_external_actions", False)
                    if auto_approve:
                        DBManager.log_auth_event(
                            user_id=user_id,
                            event_type="orchestrator_approval_auto_approved",
                            ip_address="127.0.0.1",
                            user_agent="OrchestratorEngine",
                            detail=f"Auto-approved task '{task.task_id}' ({task.task_type}) for workflow '{workflow_id}'"
                        )
                    else:
                        cls._update_task_status(workflow_id, task.task_id, TaskState.AWAITING_APPROVAL)
                        cls._update_workflow_status(workflow_id, WorkflowState.AWAITING_APPROVAL)
                        DBManager.log_auth_event(
                            user_id=user_id,
                            event_type="orchestrator_approval_submitted",
                            ip_address="127.0.0.1",
                            user_agent="OrchestratorEngine",
                            detail=f"Task '{task.task_id}' ({task.task_type}) submitted for human approval in workflow '{workflow_id}'"
                        )
                        return cls._get_workflow_schema(workflow_id, WorkflowState.AWAITING_APPROVAL)

                merged_input = cls._merge_dependency_inputs(task.input, task.dependencies, completed_task_outputs)
                task_success = False
                task_output = None
                last_error = None

                for attempt in range(max_retries + 1):
                    if cls.is_cancelled(workflow_id):
                        return cls._mark_workflow_cancelled(workflow_id)
                    cls._update_task_status(workflow_id, task.task_id, TaskState.RUNNING)
                    try:
                        task_output = await asyncio.wait_for(
                            CapabilityRegistry.execute(
                                name=task.task_type,
                                user_id=user_id,
                                input_data=merged_input
                            ),
                            timeout=min(30.0, execution_timeout)
                        )
                        task_success = True
                        break
                    except Exception as e:
                        last_error = str(e) or type(e).__name__
                        if attempt < max_retries:
                            await asyncio.sleep(0.5)

                if task_success:
                    completed_task_outputs[task.task_id] = task_output or {}
                    cls._update_task_completed(workflow_id, task.task_id, task_output)
                    pending_task_map.pop(task.task_id)
                else:
                    cls._update_task_failed(workflow_id, task.task_id, last_error or "Unknown error")
                    return cls._mark_workflow_failed(workflow_id, f"Task '{task.task_id}' ({task.task_type}) failed: {last_error}")

        return cls._mark_workflow_completed(workflow_id)

    @classmethod
    def _merge_dependency_inputs(
        cls,
        task_input: Dict[str, Any],
        dependencies: List[str],
        outputs_map: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        merged = dict(task_input)
        for dep_id in dependencies:
            dep_out = outputs_map.get(dep_id, {})
            # Merge key fields if not already explicitly provided in input
            if "skills" in dep_out and "skills" not in merged:
                merged["skills"] = dep_out["skills"]
            if "target_role" in dep_out and "target_role" not in merged:
                merged["target_role"] = dep_out["target_role"]
            if "jobs" in dep_out and len(dep_out["jobs"]) > 0 and "job_id" not in merged:
                merged["job_id"] = dep_out["jobs"][0].get("id")
                merged["job_description"] = dep_out["jobs"][0].get("description", "")
                merged["company"] = dep_out["jobs"][0].get("company", "")
        return merged

    @classmethod
    def _get_workflow_schema(
        cls,
        workflow_id: str,
        fallback_status: WorkflowState = WorkflowState.FAILED,
        fallback_error: Optional[str] = None
    ) -> WorkflowSchema:
        wf_dict = DBManager.get_workflow(workflow_id)
        if not wf_dict:
            return WorkflowSchema(
                workflow_id=workflow_id,
                user_id=0,
                goal="Unknown",
                status=fallback_status,
                error=fallback_error,
                tasks=[]
            )
        return WorkflowSchema(**wf_dict)

    @classmethod
    def _update_workflow_status(cls, workflow_id: str, status: WorkflowState):
        DBManager.update_workflow_status(workflow_id, status.value)

    @classmethod
    def _update_task_status(cls, workflow_id: str, task_id: str, status: TaskState):
        DBManager.update_task_status(workflow_id, task_id, status.value)

    @classmethod
    def _update_task_completed(cls, workflow_id: str, task_id: str, output: Optional[Dict[str, Any]]):
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')
        DBManager.update_task_output(workflow_id, task_id, TaskState.COMPLETED.value, output or {}, now_str)

    @classmethod
    def _update_task_failed(cls, workflow_id: str, task_id: str, error: str):
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')
        DBManager.update_task_error(workflow_id, task_id, TaskState.FAILED.value, error, now_str)

    @classmethod
    def _mark_workflow_completed(cls, workflow_id: str) -> WorkflowSchema:
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')
        DBManager.finish_workflow(workflow_id, WorkflowState.COMPLETED.value, completed_at=now_str)
        return cls._get_workflow_schema(workflow_id, WorkflowState.COMPLETED)

    @classmethod
    def _mark_workflow_failed(cls, workflow_id: str, error_msg: str) -> WorkflowSchema:
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')
        try:
            DBManager.finish_workflow(workflow_id, WorkflowState.FAILED.value, error=error_msg, completed_at=now_str)
        except Exception as e:
            print(f"[OrchestratorEngine] finish_workflow error: {e}")
        return cls._get_workflow_schema(workflow_id, WorkflowState.FAILED, fallback_error=error_msg)

    @classmethod
    def _mark_workflow_cancelled(cls, workflow_id: str) -> WorkflowSchema:
        now_str = datetime.now(timezone.utc).isoformat(sep=' ')
        DBManager.finish_workflow(workflow_id, WorkflowState.CANCELLED.value, error="Workflow cancelled by user.", completed_at=now_str)
        return cls._get_workflow_schema(workflow_id, WorkflowState.CANCELLED, fallback_error="Workflow cancelled by user.")
