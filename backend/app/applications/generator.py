from typing import Dict, Any, List
from app.llm.cover_letter import CoverLetterGenerator
from app.llm.resume_tailor import ResumeBulletTailor
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher

class ApplicationGenerator:
    @staticmethod
    async def generate_package(user_id: int, job_id: str, full_name: str) -> Dict[str, Any]:
        # 1. Fetch User Profile
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            raise ValueError("User profile resume text is missing. Please upload a resume.")
            
        # 2. Fetch Job Details from ChromaDB
        jobs_collection = JobMatcher.get_collection()
        job_result = jobs_collection.get(ids=[job_id])
        if not job_result or not job_result["ids"]:
            raise ValueError(f"Job with ID '{job_id}' not found in database.")
            
        job_desc = job_result["documents"][0]
        job_meta = job_result["metadatas"][0]
        
        job_title = job_meta.get("title", "Software Engineer")
        company_name = job_meta.get("company", "the company")
        
        # 3. Generate Tailored Cover Letter (Ollama)
        cover_letter = await CoverLetterGenerator.generate(
            resume_text=profile["resume_text"],
            target_role=job_title,
            company_name=company_name,
            tone="formal"
        )
        
        # Replace template markers if any
        cover_letter = cover_letter.replace("[Your Name]", full_name)
        cover_letter = cover_letter.replace("[Candidate Name]", full_name)
        
        # 4. Generate Tailored Resume Bullets (Ollama)
        resume_bullets = await ResumeBulletTailor.tailor_bullets(
            resume_text=profile["resume_text"],
            job_description=job_desc
        )
        
        # 5. Extract Key Match Highlights
        key_points = [
            f"Demonstrated experience aligning with requirements for {job_title}.",
            f"Proficient in skills highlighted in the job description: {', '.join(profile.get('skills', [])[:3])}.",
            f"Proven ability to deliver value at {company_name} in similar capacities."
        ]
        
        # 6. Suggested Email Subject Line
        subject_line = f"Application for {job_title} - {full_name}"
        
        return {
            "cover_letter": cover_letter,
            "resume_bullets": resume_bullets,
            "key_points": key_points,
            "suggested_subject_line": subject_line
        }
