from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.orchestrator.enums import WorkflowState, TaskState

class TaskSchema(BaseModel):
    task_id: str
    workflow_id: str
    task_type: str
    description: str
    status: TaskState = TaskState.PENDING
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[Dict[str, Any]] = None
    dependencies: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

class WorkflowSchema(BaseModel):
    workflow_id: str
    user_id: int
    goal: str
    status: WorkflowState = WorkflowState.PENDING
    tasks: List[TaskSchema] = Field(default_factory=list)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

class WorkflowCreateRequest(BaseModel):
    goal: str
    max_steps: Optional[int] = Field(default=10, ge=1, le=20)
    execution_timeout: Optional[float] = Field(default=120.0, ge=0.01, le=600.0)
    max_retries: Optional[int] = Field(default=2, ge=0, le=5)

class PlanTaskSpec(BaseModel):
    task_id: str
    task_type: str
    description: str
    input: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)

class PlanSchema(BaseModel):
    tasks: List[PlanTaskSpec]
