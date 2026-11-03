import json
import re
import uuid
from typing import List, Dict, Any, Optional
from app.llm.ollama_client import OllamaClient
from app.orchestrator.capabilities import CapabilityRegistry
from app.orchestrator.schemas import PlanSchema, PlanTaskSpec

class GoalPlanner:
    """
    Translates a high-level user goal into a structured task execution plan.
    Strictly constrained to select ONLY approved capabilities registered in CapabilityRegistry.
    """

    @classmethod
    async def create_plan(cls, goal: str, max_steps: Optional[int] = 10) -> PlanSchema:
        steps_limit = max_steps or 10
        capabilities = CapabilityRegistry.get_all()
        cap_descriptions = "\n".join([
            f"- '{cap['name']}': {cap['description']}"
            for cap in capabilities.values()
        ])

        system_prompt = (
            "You are the central Agent Orchestrator for the AI Powered Assistance Platform Career Copilot. "
            "Your job is to break down a high-level user goal into an ordered sequence of executable tasks. "
            "You MUST ONLY select task types from the list of approved capabilities provided below. "
            "Do NOT invent new task types or execute raw code/shell commands. "
            "You MUST respond ONLY in valid JSON. No commentary before or after JSON."
        )

        prompt = f"""
Approved Capabilities:
{cap_descriptions}

User Goal:
"{goal}"

Instructions:
1. Create a task execution plan consisting of 1 to {steps_limit} steps to fulfill the user's goal.
2. For each task, set:
   - "task_id": "task_1", "task_2", etc.
   - "task_type": MUST be one of the approved capability names strictly.
   - "description": clear summary of what this task step does.
   - "input": dictionary of parameters for the capability (e.g. {{"target_role": "Python Developer", "search_term": "Python"}}).
   - "dependencies": list of preceding task_ids that must complete before this task starts (e.g. ["task_1"]).

Format JSON Output:
{{
  "tasks": [
    {{
      "task_id": "task_1",
      "task_type": "analyze_resume",
      "description": "Analyze user resume skills and current background",
      "input": {{}},
      "dependencies": []
    }},
    {{
      "task_id": "task_2",
      "task_type": "search_and_match_jobs",
      "description": "Find Python developer job postings matching user profile",
      "input": {{"search_term": "Python Developer", "location": "Bengaluru"}},
      "dependencies": ["task_1"]
    }}
  ]
}}

Return ONLY valid JSON.
"""
        try:
            raw_response = await OllamaClient.generate(
                prompt=prompt,
                system=system_prompt,
                format="json"
            )
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            plan = PlanSchema(**data)
            
            # Validate plan tasks
            if not plan.tasks:
                raise ValueError("Plan contains no tasks.")
            if len(plan.tasks) > steps_limit:
                plan.tasks = plan.tasks[:steps_limit]

            for task in plan.tasks:
                if not CapabilityRegistry.is_valid_capability(task.task_type):
                    raise ValueError(f"Task '{task.task_id}' requested unapproved capability '{task.task_type}'.")

            return plan

        except Exception as e:
            print(f"[GoalPlanner] LLM Planning failed: {e}. Falling back to default plan.")
            # Fallback heuristic plan if LLM output fails validation
            return cls._fallback_plan(goal)

    @classmethod
    def _fallback_plan(cls, goal: str) -> PlanSchema:
        goal_lower = goal.lower()

        tasks: List[PlanTaskSpec] = []
        tasks.append(PlanTaskSpec(
            task_id="task_1",
            task_type="analyze_resume",
            description="Analyze resume profile and skills",
            input={},
            dependencies=[]
        ))

        if any(w in goal_lower for w in ["job", "match", "search", "find", "apply"]):
            tasks.append(PlanTaskSpec(
                task_id="task_2",
                task_type="search_and_match_jobs",
                description="Search for matching job listings",
                input={"search_term": goal, "limit": 5},
                dependencies=["task_1"]
            ))
        elif any(w in goal_lower for w in ["gap", "skill", "learn", "roadmap"]):
            tasks.append(PlanTaskSpec(
                task_id="task_2",
                task_type="analyze_skill_gap",
                description="Analyze skill gaps for goal role",
                input={"target_role": goal},
                dependencies=["task_1"]
            ))
        else:
            tasks.append(PlanTaskSpec(
                task_id="task_2",
                task_type="career_copilot_query",
                description="Consult career copilot for guidance",
                input={"query": goal},
                dependencies=["task_1"]
            ))

        return PlanSchema(tasks=tasks)
