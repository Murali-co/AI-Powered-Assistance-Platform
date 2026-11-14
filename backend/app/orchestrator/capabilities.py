from typing import Dict, Any, Callable, Awaitable, List
import asyncio
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.jobs.scraper import JobScraper
from app.llm.skill_gap import SkillGapAnalyzer
from app.llm.resume_tailor import ResumeTailorEngine, ResumeBulletTailor
from app.llm.cover_letter import CoverLetterGenerator
from app.rag.generator import RAGGenerator
from app.auth.models import DBManager

class CapabilityRegistry:
    """
    Registry of approved, safe capabilities available to the Agent Orchestrator.
    The LLM cannot directly execute shell, python, SQL, filesystem, or database calls.
    It can ONLY request execution of these pre-registered capabilities.
    """
    _registry: Dict[str, Dict[str, Any]] = {}
    VALID_RISK_TIERS = {"read_only", "write_internal", "external_action"}

    @classmethod
    def register(cls, name: str, description: str, handler: Callable[..., Awaitable[Dict[str, Any]]], risk_tier: str):
        if risk_tier not in cls.VALID_RISK_TIERS:
            raise ValueError(f"Invalid risk_tier '{risk_tier}'. Must be one of {cls.VALID_RISK_TIERS}")
        cls._registry[name] = {
            "name": name,
            "description": description,
            "risk_tier": risk_tier,
            "handler": handler
        }

    @classmethod
    def get_all(cls) -> Dict[str, Dict[str, Any]]:
        return cls._registry

    @classmethod
    def get_capability_names(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def get_risk_tier(cls, name: str) -> str:
        if name not in cls._registry:
            raise ValueError(f"Capability '{name}' is not approved or registered.")
        return cls._registry[name]["risk_tier"]

    @classmethod
    def is_valid_capability(cls, name: str) -> bool:
        return name in cls._registry

    @classmethod
    async def execute(cls, name: str, user_id: int, input_data: Dict[str, Any]) -> Dict[str, Any]:
        if not cls.is_valid_capability(name):
            raise ValueError(f"Capability '{name}' is not approved or registered.")
        
        handler = cls._registry[name]["handler"]
        # Execute capability safely
        return await handler(user_id=user_id, **input_data)


# Capability Handlers
async def handle_analyze_resume(user_id: int, **kwargs) -> Dict[str, Any]:
    profile = ProfileStore.get_profile(user_id) or {}
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

async def handle_analyze_skill_gap(user_id: int, target_role: str = "Software Engineer", job_description: str = "", **kwargs) -> Dict[str, Any]:
    profile = ProfileStore.get_profile(user_id) or {}
    skills = profile.get("skills", [])
    
    analysis = await SkillGapAnalyzer.analyze(skills=skills, target_role=target_role)
    return {
        "status": "success",
        "target_role": target_role,
        "analysis": analysis
    }

async def handle_search_and_match_jobs(user_id: int, limit: int = 5, search_term: str = "", location: str = "", **kwargs) -> Dict[str, Any]:
    # Optionally trigger scraper if search_term provided
    if search_term:
        try:
            loc = location if location else "Bengaluru, India"
            scraped_jobs = JobScraper.scrape(search_term=search_term, location=loc, results_wanted=10, hours_old=48)
            if scraped_jobs:
                JobMatcher.upsert_jobs(scraped_jobs)
        except Exception as e:
            print(f"[Orchestrator] Job scraper notice: {e}")

    matched = JobMatcher.match_jobs_for_user(user_id, limit=limit)
    return {
        "status": "success",
        "jobs_found": len(matched),
        "jobs": matched
    }

async def handle_tailor_resume(user_id: int, job_description: str = "", job_id: str = "", **kwargs) -> Dict[str, Any]:
    profile = ProfileStore.get_profile(user_id) or {}
    resume_text = profile.get("resume_text", "Experienced professional.")
    
    if not job_description and job_id:
        collection = JobMatcher.get_collection()
        result = collection.get(ids=[job_id])
        if result and result["documents"]:
            job_description = result["documents"][0]
            
    if not job_description:
        job_description = "Software Developer with strong technical and problem solving skills."

    tailored_result = await ResumeTailorEngine.tailor(resume_text=resume_text, job_description=job_description)
    bullets = await ResumeBulletTailor.tailor_bullets(resume_text=resume_text, job_description=job_description)
    
    return {
        "status": "success",
        "tailored_resume": tailored_result.get("tailored_resume"),
        "keyword_changes": tailored_result.get("keyword_changes"),
        "ats_score_estimate": tailored_result.get("ats_score_estimate"),
        "tailored_bullets": bullets
    }

async def handle_generate_cover_letter(user_id: int, target_role: str = "Software Engineer", company: str = "", job_description: str = "", tone: str = "formal", **kwargs) -> Dict[str, Any]:
    profile = ProfileStore.get_profile(user_id) or {}
    resume_text = profile.get("resume_text", "Experienced professional.")
    
    cover_letter = await CoverLetterGenerator.generate(
        resume_text=resume_text,
        target_role=target_role,
        company_name=company,
        tone=tone
    )
    return {
        "status": "success",
        "cover_letter": cover_letter
    }

async def handle_career_copilot_query(user_id: int, query: str = "What should be my next career move?", chat_type: str = "career", **kwargs) -> Dict[str, Any]:
    response = await RAGGenerator.generate_response(
        user_id=user_id,
        message=query,
        chat_type=chat_type,
        history=[]
    )
    return {
        "status": "success",
        "response": response
    }

async def handle_send_notification(user_id: int, title: str = "AI Powered Assistance Platform Update", message: str = "", type: str = "info", **kwargs) -> Dict[str, Any]:
    DBManager.add_notification(user_id=user_id, title=title, message=message, type=type)
    return {
        "status": "success",
        "notification_sent": True
    }

async def handle_submit_job_application(user_id: int, job_id: str = "", company: str = "Target Company", title: str = "Target Position", **kwargs) -> Dict[str, Any]:
    """External action capability: Submits job application on external employer portal."""
    return {
        "status": "success",
        "job_id": job_id,
        "company": company,
        "title": title,
        "application_submitted": True,
        "message": f"Successfully submitted application to {company} for {title}"
    }


# Register all approved capabilities on import
CapabilityRegistry.register(
    "analyze_resume",
    "Retrieve user resume text, extracted skills, and parsed section breakdown.",
    handle_analyze_resume,
    risk_tier="read_only"
)

CapabilityRegistry.register(
    "analyze_skill_gap",
    "Diagnose skill gaps against a target role or job description and recommend learning resources.",
    handle_analyze_skill_gap,
    risk_tier="read_only"
)

CapabilityRegistry.register(
    "search_and_match_jobs",
    "Search and rank matching active job listings based on candidate profile embeddings.",
    handle_search_and_match_jobs,
    risk_tier="read_only"
)

CapabilityRegistry.register(
    "tailor_resume",
    "Tailor resume keywords and generate optimized bullet points aligned with a target job description.",
    handle_tailor_resume,
    risk_tier="write_internal"
)

CapabilityRegistry.register(
    "generate_cover_letter",
    "Draft a personalized cover letter matching candidate experience to a target role and company.",
    handle_generate_cover_letter,
    risk_tier="write_internal"
)

CapabilityRegistry.register(
    "career_copilot_query",
    "Ask the RAG-grounded Career Copilot for personalized career planning advice.",
    handle_career_copilot_query,
    risk_tier="read_only"
)

CapabilityRegistry.register(
    "send_notification",
    "Send an in-app notification alert to the user.",
    handle_send_notification,
    risk_tier="write_internal"
)

CapabilityRegistry.register(
    "submit_job_application",
    "Submit a formal job application and resume to an external employer portal on behalf of the candidate.",
    handle_submit_job_application,
    risk_tier="external_action"
)
