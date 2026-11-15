from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: Dict[str, Any] = {}


class ToolExecutionResult(BaseModel):
    tool: str
    result: Any
    error: Optional[str] = None


class ToolDefinitionSchema(BaseModel):
    name: str
    description: str
    permissions: List[str] = []
