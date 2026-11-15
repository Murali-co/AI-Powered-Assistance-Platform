from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .adaptive_engine import AdaptiveInterviewEngine

router = APIRouter(prefix="/interview", tags=["interview"])
engine = AdaptiveInterviewEngine()


class InterviewPromptRequest(BaseModel):
    question_index: int = 0


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1)


@router.get("/health")
async def interview_health() -> Dict[str, str]:
    return {"status": "ok", "service": "interview"}


@router.get("/next-question")
async def next_question(question_index: int = 0) -> Dict[str, Any]:
    question = engine.next_question(question_index)
    if question is None:
        return {"question": None, "completed": True}
    return {"question": question.prompt, "id": question.id, "completed": False}


@router.post("/score")
async def score_answer(payload: InterviewAnswerRequest) -> Dict[str, Any]:
    return engine.build_feedback(payload.answer)
