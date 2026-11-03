import json
import re
from typing import List, Dict, Any
from app.llm.ollama_client import OllamaClient
from app.models.schemas import SkillGapResponse

class SkillGapAnalyzer:
    @staticmethod
    async def analyze(skills: List[str], target_role: str) -> Dict[str, Any]:
        system_prompt = (
            "You are a professional technical recruiter and career coach. Your task is to perform "
            "a skill gap analysis based on a candidate's current skills and their target job role. "
            "You MUST respond ONLY in valid JSON. Do not include any text before or after the JSON payload."
        )

        # Truncate to reduce token usage
        skills_str = ", ".join(skills[:30])  # cap at 30 skills

        prompt = f"""
Candidate's Current Skills: {skills_str}
Target Job Role: {target_role}

Please analyze the skill gap and return a JSON object with the following fields:
1. "present_skills": list of skills the candidate already possesses that are highly relevant to the target role.
2. "missing_skills": list of critical skills/technologies/methodologies required for the target role that the candidate currently lacks.
3. "skill_score": an integer from 0 to 100 representing how closely the candidate's current skills match the target role.
4. "recommendations": bullet points suggesting how the candidate can bridge the skill gap (e.g. projects, certifications).
5. "learning_resources": high-quality resource suggestions (e.g., online courses, books, documentation links).

Example response format:
{{
  "present_skills": ["Python", "Docker"],
  "missing_skills": ["Kubernetes", "Go"],
  "skill_score": 65,
  "recommendations": ["Build a multi-container app and deploy to Kubernetes.", "Learn Go syntax and build a REST API."],
  "learning_resources": ["Official Kubernetes Documentation (kubernetes.io)", "Learn Go on tour.golang.org"]
}}

Return ONLY valid JSON.
"""

        try:
            raw_response = await OllamaClient.generate(
                prompt=prompt,
                system=system_prompt,
                format="json"
            )
            
            # Clean response if LLM added markdown wrappers
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                # strip code block markers
                cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
                cleaned = re.sub(r"\n```$", "", cleaned)
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            
            # Validate with Pydantic
            validated = SkillGapResponse(**data)
            return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
            
        except Exception as e:
            print(f"Error parsing skill gap JSON from Ollama: {e}")
            # Fallback response in case of parsing failures
            return {
                "present_skills": [s for s in skills if s.lower() in target_role.lower()] or skills[:3],
                "missing_skills": ["Cloud Architecture", "System Design", "Advanced " + target_role],
                "skill_score": 50,
                "recommendations": ["Conduct deep research on target technologies for " + target_role, "Work on building a complete side project."],
                "learning_resources": ["Explore tutorials and courses related to " + target_role]
            }
