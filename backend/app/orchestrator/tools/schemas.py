from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Type
from app.orchestrator.tools.permissions import ToolPermission

class ToolDefinitionSchema(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    permission: ToolPermission = ToolPermission.EXECUTE
    timeout: float = Field(default=30.0, ge=0.1, le=300.0)
    enabled: bool = True

class ToolExecutionRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

class ToolExecutionResult(BaseModel):
    tool_name: str
    status: str  # "SUCCESS", "FAILED", "TIMEOUT", "UNAUTHORIZED", "INVALID_ARGS"
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0

class LLMToolCallPayload(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
