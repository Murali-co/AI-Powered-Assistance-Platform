from __future__ import annotations

from typing import List

from .enums import StepType, TaskStatus
from .models import PlanStep, Task, TaskPlan


class TaskPlanner:
    """Produces a lightweight plan for a user query."""

    def build_plan(self, task: Task) -> TaskPlan:
        prompt = task.prompt.lower()
        steps: List[PlanStep] = []

        if "resume" in prompt or "cv" in prompt:
            steps.append(PlanStep("analyze_resume", "Review resume data and extract skills.", StepType.ANALYZE.value, {"kind": "resume"}))
        else:
            steps.append(PlanStep("analyze_context", "Inspect the request context and constraints.", StepType.ANALYZE.value, {"kind": "general"}))

        steps.append(PlanStep("draft_plan", "Create a practical execution plan.", StepType.PLAN.value, {}))
        steps.append(PlanStep("execute", "Run the focused strategy against available tools.", StepType.EXECUTE.value, {}))
        steps.append(PlanStep("verify", "Validate the outcome and summarize findings.", StepType.VERIFY.value, {}))

        return TaskPlan(task.task_id, task.prompt, steps)
