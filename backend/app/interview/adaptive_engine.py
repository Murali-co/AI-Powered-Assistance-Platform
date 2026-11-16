from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class InterviewQuestion:
    id: str
    prompt: str
    difficulty: str = "medium"


@dataclass
class InterviewRound:
    question: InterviewQuestion
    answer: Optional[str] = None
    score: float = 0.0


class AdaptiveInterviewEngine:
    """Simple adaptive interview engine for coaching flows."""

    def __init__(self) -> None:
        self._questions: List[InterviewQuestion] = [
            InterviewQuestion("intro", "Tell me about yourself and your background."),
            InterviewQuestion("strengths", "What are your strongest technical skills?"),
            InterviewQuestion("scenario", "Describe a difficult challenge you solved recently."),
        ]

    def next_question(self, completed: int = 0) -> Optional[InterviewQuestion]:
        if completed >= len(self._questions):
            return None
        return self._questions[completed]

    async def score_answer(self, answer: str, question: str) -> float:
        from .service import evaluate
        return (await evaluate(question, answer, 3))['score'] / 100

    async def build_feedback(self, answer: str, question: str) -> Dict[str, object]:
        from .service import evaluate
        return await evaluate(question, answer, 3)
