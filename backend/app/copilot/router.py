from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: Optional[Dict[str, Any]] = None


class CopilotResponse(BaseModel):
    answer: str
    mode: str = "copilot"


@router.get("/health")
async def copilot_health() -> Dict[str, str]:
    return {"status": "ok", "service": "copilot"}


@router.post("/respond", response_model=CopilotResponse)
async def respond_to_prompt(payload: CopilotRequest) -> CopilotResponse:
    summary = payload.context or {}
    prompt_text = payload.prompt.strip()
    context_text = " " + str(summary) if summary else ""
    return CopilotResponse(
        answer=f"Copilot response for: {prompt_text}{context_text}",
        mode="copilot",
    )
