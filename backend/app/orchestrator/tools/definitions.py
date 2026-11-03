from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.jobs.scraper import JobScraper
from app.llm.skill_gap import SkillGapAnalyzer
from app.llm.resume_tailor import ResumeTailorEngine, ResumeBulletTailor
from app.llm.cover_letter import CoverLetterGenerator
from app.llm.ollama_client import OllamaClient
from app.rag.generator import RAGGenerator
from app.rag.retriever import RAGRetriever
from app.auth.models import DBManager
from app.config import settings
from app.orchestrator.tools.permissions import ToolPermission
from starlette.concurrency import run_in_threadpool

# ==================== TOOL 1: get_user_resume ====================
class GetUserResumeInput(BaseModel):
    pass

class GetUserResumeOutput(BaseModel):
    status: str
    skills: List[str]
    resume_text: str
    sections: List[str]

async def handle_get_user_resume(user_id: int, **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    skills = profile.get("skills", [])
    resume_text = profile.get("resume_text", "")
    sections = profile.get("sections", {})
    return {
        "status": "success",
        "skills": skills,
        "resume_text": resume_text,
        "sections": list(sections.keys()) if isinstance(sections, dict) else []
    }

# ==================== TOOL 2: analyze_resume ====================
class AnalyzeResumeInput(BaseModel):
    query: Optional[str] = Field(default="", description="Optional focus keyword or topic for resume extraction")

class AnalyzeResumeOutput(BaseModel):
    status: str
    skills_count: int
    skills: List[str]
    resume_text: str
    sections: List[str]

async def handle_analyze_resume(user_id: int, query: str = "", **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    skills = profile.get("skills", [])
    resume_text = profile.get("resume_text", "")
    sections = profile.get("sections", {})
    return {
        "status": "success",
        "skills_count": len(skills),
        "skills": skills,
        "resume_text": resume_text,
        "sections": list(sections.keys()) if isinstance(sections, dict) else []
    }

# ==================== TOOL 3: rag_search ====================
class RAGSearchInput(BaseModel):
    query: str = Field(description="Search query to retrieve grounded context")
    chat_type: str = Field(default="career", description="Routing mode: 'resume', 'job', or 'career'")

class RAGSearchOutput(BaseModel):
    status: str
    query: str
    chat_type: str
    response: str

async def handle_rag_search(user_id: int, query: str, chat_type: str = "career", **kwargs) -> Dict[str, Any]:
    response = await RAGGenerator.generate_response(
        user_id=user_id,
        message=query,
        chat_type=chat_type,
        history=[]
    )
    return {
        "status": "success",
        "query": query,
        "chat_type": chat_type,
        "response": response
    }

# ==================== TOOL 4: search_jobs ====================
class SearchJobsInput(BaseModel):
    search_term: str = Field(description="Job title or search keyword e.g. 'Python Developer'")
    location: Optional[str] = Field(default="Bengaluru, India", description="Target city/location")
    limit: Optional[int] = Field(default=5, ge=1, le=20)

class SearchJobsOutput(BaseModel):
    status: str
    search_term: str
    jobs_found: int
    jobs: List[Dict[str, Any]]

async def handle_search_jobs(user_id: int, search_term: str, location: str = "Bengaluru, India", limit: int = 5, **kwargs) -> Dict[str, Any]:
    matched = await run_in_threadpool(JobMatcher.match_jobs_for_user, user_id, limit=limit)
    return {
        "status": "success",
        "search_term": search_term,
        "jobs_found": len(matched),
        "jobs": matched
    }

# ==================== TOOL 5: match_jobs ====================
class MatchJobsInput(BaseModel):
    limit: Optional[int] = Field(default=5, ge=1, le=20)

class MatchJobsOutput(BaseModel):
    status: str
    jobs_matched: int
    jobs: List[Dict[str, Any]]

async def handle_match_jobs(user_id: int, limit: int = 5, **kwargs) -> Dict[str, Any]:
    matched = await run_in_threadpool(JobMatcher.match_jobs_for_user, user_id, limit=limit)
    return {
        "status": "success",
        "jobs_matched": len(matched),
        "jobs": matched
    }

# ==================== TOOL 6: analyze_skill_gap ====================
class AnalyzeSkillGapInput(BaseModel):
    target_role: str = Field(description="Target job title e.g. 'Senior Backend Engineer'")

class AnalyzeSkillGapOutput(BaseModel):
    status: str
    target_role: str
    analysis: Dict[str, Any]

async def handle_analyze_skill_gap(user_id: int, target_role: str, **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    skills = profile.get("skills", [])
    analysis = await SkillGapAnalyzer.analyze(skills=skills, target_role=target_role)
    return {
        "status": "success",
        "target_role": target_role,
        "analysis": analysis
    }

# ==================== TOOL 7: tailor_resume ====================
class TailorResumeInput(BaseModel):
    job_description: Optional[str] = Field(default="", description="Target job description text")
    job_id: Optional[str] = Field(default="", description="ID of saved/matched job listing")

class TailorResumeOutput(BaseModel):
    status: str
    tailored_resume: str
    keyword_changes: List[Dict[str, Any]]
    ats_score_estimate: int
    tailored_bullets: List[str]

async def handle_tailor_resume(user_id: int, job_description: str = "", job_id: str = "", **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    resume_text = profile.get("resume_text", "Experienced professional.")
    
    if not job_description and job_id:
        collection = JobMatcher.get_collection()
        result = await run_in_threadpool(collection.get, ids=[job_id])
        if result and result["documents"]:
            job_description = result["documents"][0]

    if not job_description:
        job_description = "Software Engineer position requiring strong coding, system design, and API optimization skills."

    tailored_result = await ResumeTailorEngine.tailor(resume_text=resume_text, job_description=job_description)
    bullets = await ResumeBulletTailor.tailor_bullets(resume_text=resume_text, job_description=job_description)

    return {
        "status": "success",
        "tailored_resume": tailored_result.get("tailored_resume", resume_text),
        "keyword_changes": tailored_result.get("keyword_changes", []),
        "ats_score_estimate": tailored_result.get("ats_score_estimate", 85),
        "tailored_bullets": bullets
    }

# ==================== TOOL 8: generate_interview_questions ====================
class GenerateInterviewQuestionsInput(BaseModel):
    target_role: str = Field(description="Target role for mock interview questions")
    question_count: Optional[int] = Field(default=3, ge=1, le=10)

class GenerateInterviewQuestionsOutput(BaseModel):
    status: str
    target_role: str
    questions: List[str]

async def handle_generate_interview_questions(user_id: int, target_role: str = "Software Engineer", question_count: int = 3, **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    skills = profile.get("skills", [])
    skills_str = ", ".join(skills[:10])

    prompt = f"""
Target Role: {target_role}
Candidate Skills: {skills_str}

Please generate {question_count} realistic, technical & behavioral mock interview questions for this target role.
Return ONLY plain text bullet points starting with '- '.
"""
    try:
        raw_res = await OllamaClient.generate(prompt=prompt)
        lines = [line.strip().lstrip("-*123456789. ").strip() for line in raw_res.split("\n") if line.strip()]
        questions = [q for q in lines if len(q) > 10][:question_count]
        if not questions:
            raise ValueError("No questions parsed")
    except Exception:
        questions = [
            f"Tell me about a challenging technical problem you solved while working with {skills[0] if skills else 'software architecture'}.",
            f"How do you design scalable RESTful microservices for a {target_role} position?",
            f"Describe how you handle tight project deadlines and code reviews under pressure."
        ][:question_count]

    return {
        "status": "success",
        "target_role": target_role,
        "questions": questions
    }

# ==================== TOOL 9: generate_career_roadmap ====================
class GenerateCareerRoadmapInput(BaseModel):
    target_role: str = Field(description="Target goal role for career transition e.g. 'Machine Learning Engineer'")

class GenerateCareerRoadmapOutput(BaseModel):
    status: str
    target_role: str
    roadmap_steps: List[str]

async def handle_generate_career_roadmap(user_id: int, target_role: str, **kwargs) -> Dict[str, Any]:
    profile = (await run_in_threadpool(ProfileStore.get_profile, user_id)) or {}
    skills = profile.get("skills", [])
    
    prompt = f"""
Current Skills: {', '.join(skills[:15])}
Target Role: {target_role}

Provide a 4-step actionable career transition roadmap to achieve this target role.
Format output as 4 bullet points starting with 'Step 1:', 'Step 2:', etc.
"""
    try:
        raw_res = await OllamaClient.generate(prompt=prompt)
        steps = [line.strip() for line in raw_res.split("\n") if line.strip() and ("step" in line.lower() or line.startswith(("-", "*", "1", "2", "3", "4")))]
        if len(steps) < 2:
            raise ValueError("Roadmap parse failure")
    except Exception:
        steps = [
            f"Step 1: Solidify foundational principles for {target_role}.",
            f"Step 2: Build end-to-end portfolio projects incorporating missing core skills.",
            f"Step 3: Gain certification and hands-on exposure to production deployment.",
            f"Step 4: Tailor resume and apply for intermediate roles matching the trajectory."
        ]

    return {
        "status": "success",
        "target_role": target_role,
        "roadmap_steps": steps
    }

# ==================== TOOL 10: get_user_profile ====================
class GetUserProfileInput(BaseModel):
    pass

class GetUserProfileOutput(BaseModel):
    status: str
    user_id: int
    email: str
    full_name: str
    is_admin: bool
    preferred_model: str
    search_criteria: Dict[str, Any]

async def handle_get_user_profile(user_id: int, **kwargs) -> Dict[str, Any]:
    user = (await run_in_threadpool(DBManager.get_user_by_id, user_id)) or {}
    criteria = (await run_in_threadpool(DBManager.get_criteria, user_id)) or {}
    return {
        "status": "success",
        "user_id": user_id,
        "email": user.get("email", ""),
        "full_name": user.get("full_name", "User"),
        "is_admin": bool(user.get("is_admin", False)),
        "preferred_model": user.get("preferred_model", settings.OLLAMA_MODEL),
        "search_criteria": criteria
    }
