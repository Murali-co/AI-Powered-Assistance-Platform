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

    def score_answer(self, answer: str) -> float:
        cleaned = (answer or "").strip()
        if not cleaned:
            return 0.0
        return min(1.0, max(0.1, len(cleaned) / 250.0))

    def build_feedback(self, answer: str) -> Dict[str, object]:
        score = self.score_answer(answer)
        return {
            "score": round(score, 3),
            "status": "strong" if score >= 0.7 else "needs_improvement",
            "tip": "Use specific examples, measurable impact, and results.",
        }
