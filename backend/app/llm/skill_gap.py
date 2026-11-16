from fastapi import HTTPException
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

        known = {skill.strip().casefold(): skill.strip() for skill in skills if isinstance(skill, str) and skill.strip()}
        if len(known) > 100 or any(len(skill) > 100 for skill in known.values()):
            raise HTTPException(422, 'Use at most 100 concise skill labels for one analysis.')
        skills_str = json.dumps(list(known.values()))
        schema = SkillGapResponse.model_json_schema()
        if known:
            schema['properties']['present_skills']['items'] = {'type': 'string', 'enum': list(known.values())}
        else:
            schema['properties']['present_skills']['maxItems'] = 0

        prompt = f"""
Candidate's Current Skills: {skills_str}
Target Job Role: {target_role}

Please analyze the skill gap and return a JSON object with the following fields:
1. "present_skills": select only exact labels from Candidate's Current Skills. Never infer qualifications or experience.
2. "missing_skills": list of critical skills/technologies/methodologies required for the target role that the candidate currently lacks. Never include a listed current skill here.
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
                format=schema
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
            if any(skill.strip().casefold() not in known for skill in validated.present_skills):
                raise ValueError('Model claimed a skill absent from the candidate profile.')
            if any(skill.strip().casefold() in known for skill in validated.missing_skills):
                raise ValueError('Model marked an existing candidate skill as missing.')
            return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
            
        except Exception:
            raise HTTPException(503, 'Local AI could not produce a valid skill-gap analysis. Please retry.') from None
