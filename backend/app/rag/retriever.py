from typing import List, Dict, Any, Optional
import json
import logging
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.auth.models import DBManager
from app.vector_db.embedder import embed_text
from app.db.session import SessionLocal
from app.db.models import ResumeVersion, SavedJob

logger = logging.getLogger(__name__)


class RAGRetriever:
    @classmethod
    def get_resume_context(
        cls, 
        user_id: int, 
        query: str = "", 
        resume_version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves user resume text, skills, and semantically matching resume sections
        from Neon PostgreSQL and ChromaDB.
        """
        db = SessionLocal()
        version = None
        try:
            if resume_version_id is not None:
                version = db.query(ResumeVersion).filter(
                    ResumeVersion.id == resume_version_id,
                    ResumeVersion.user_id == user_id
                ).first()
            if not version:
                version = db.query(ResumeVersion).filter(
                    ResumeVersion.user_id == user_id,
                    ResumeVersion.is_active.is_(True)
                ).first()
            if not version:
                version = db.query(ResumeVersion).filter(
                    ResumeVersion.user_id == user_id
                ).order_by(ResumeVersion.created_at.desc()).first()
        finally:
            db.close()

        skills: List[str] = []
        resume_text = ""
        version_id = None
        version_label = None

        if version:
            resume_text = version.resume_text or ""
            version_id = version.id
            version_label = version.version_label
            if version.structured_data:
                try:
                    data = json.loads(version.structured_data)
                    skills = data.get("skills", [])
                except Exception:
                    skills = []
        else:
            profile = ProfileStore.get_profile(user_id) or {}
            skills = profile.get("skills", [])
            resume_text = profile.get("resume_text", "")

        has_context = bool(resume_text.strip() or skills)

        matching_sections = []
        sections_context = ""
        if has_context and query.strip():
            try:
                matching_sections = ProfileStore.query_profile_sections(user_id, query, n_results=3)
                sections_context = "\n\n".join([
                    f"--- Section: {item['metadata'].get('section_name', 'Experience')} ---\n{item['document']}"
                    for item in matching_sections
                ])
            except Exception as e:
                logger.warning(f"Failed to query profile sections from Chroma: {e}")

        return {
            "has_context": has_context,
            "version_id": version_id,
            "version_label": version_label,
            "skills": skills,
            "full_resume": resume_text,
            "relevant_sections": sections_context,
            "raw_sections": matching_sections
        }

    @classmethod
    def get_job_context(
        cls, 
        user_id: int, 
        job_id: str, 
        resume_version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves target job details, match metrics, missing skills, and relevant user sections.
        """
        all_matches = []
        try:
            all_matches = JobMatcher.match_jobs_for_user(user_id)
        except Exception as e:
            logger.warning(f"Error matching jobs for user {user_id}: {e}")

        job_match = next((j for j in all_matches if str(j.get("id")) == str(job_id)), None)

        if not job_match:
            try:
                collection = JobMatcher.get_collection()
                result = collection.get(ids=[str(job_id)])
                if result and result["ids"]:
                    meta = result["metadatas"][0] if result["metadatas"] else {}
                    job_match = {
                        "id": str(job_id),
                        "title": meta.get("title", "Target Role"),
                        "company": meta.get("company", "Company"),
                        "description": result["documents"][0] if result["documents"] else "",
                        "match_score": 0.0,
                        "matched_skills": [],
                        "missing_skills": []
                    }
            except Exception as e:
                logger.warning(f"Error fetching job from collection: {e}")

        if not job_match or not job_match.get("description"):
            # Also check SavedJob in Neon if available
            db = SessionLocal()
            try:
                sj = db.query(SavedJob).filter(
                    SavedJob.user_id == user_id,
                    SavedJob.job_id == str(job_id)
                ).first()
                if sj:
                    job_title = getattr(sj, "job_title", getattr(sj, "title", "Target Role"))
                    job_match = {
                        "id": str(job_id),
                        "title": job_title or "Target Role",
                        "company": sj.company or "Company",
                        "description": getattr(sj, "notes", "") or "Target role details",
                        "match_score": 0.0,
                        "matched_skills": [],
                        "missing_skills": []
                    }
            except Exception:
                pass
            finally:
                db.close()

        if not job_match:
            return {
                "job": None,
                "relevant_resume_sections": "",
                "has_context": False,
                "resume_context": {}
            }

        resume_ctx = cls.get_resume_context(
            user_id, 
            query=job_match.get("description", ""), 
            resume_version_id=resume_version_id
        )

        matching_sections = []
        sections_context = ""
        if resume_ctx["has_context"] and job_match.get("description"):
            try:
                matching_sections = ProfileStore.query_profile_sections(user_id, job_match["description"], n_results=3)
                sections_context = "\n\n".join([
                    f"--- Resume section relevant to job: {item['metadata'].get('section_name', 'Experience')} ---\n{item['document']}"
                    for item in matching_sections
                ])
            except Exception as e:
                logger.warning(f"Error querying resume sections for job match: {e}")

        return {
            "job": job_match,
            "relevant_resume_sections": sections_context or resume_ctx.get("relevant_sections", ""),
            "has_context": resume_ctx.get("has_context", False),
            "resume_context": resume_ctx
        }

    @classmethod
    def get_career_context(
        cls, 
        user_id: int, 
        query: str = "", 
        resume_version_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves user profile and searches active job listings semantically 
        to ground career guidance in actual market demands.
        """
        resume_ctx = cls.get_resume_context(user_id, query=query, resume_version_id=resume_version_id)
        skills = resume_ctx.get("skills", [])

        relevant_jobs = []
        try:
            collection = JobMatcher.get_collection()
            total_jobs = collection.count()
            if total_jobs > 0 and query.strip():
                effective_n_results = min(3, total_jobs)
                query_emb = embed_text(query)
                results = collection.query(
                    query_embeddings=[query_emb],
                    n_results=effective_n_results
                )
                if results and results["ids"] and results["ids"][0]:
                    for i in range(len(results["ids"][0])):
                        relevant_jobs.append({
                            "title": results["metadatas"][0][i].get("title", "Unknown"),
                            "company": results["metadatas"][0][i].get("company", "Unknown"),
                            "description": results["documents"][0][i]
                        })
        except Exception as e:
            logger.warning(f"Error querying Chroma market jobs: {e}")

        trajectory = []
        try:
            applications = DBManager.get_applications(user_id)
            trajectory = [
                f"Applied to {app.get('job_title', 'Role')} at {app.get('company', 'Company')} (Status: {app.get('status', 'Submitted')})"
                for app in applications[:5]
            ]
        except Exception as e:
            logger.warning(f"Error fetching application history: {e}")

        return {
            "has_context": resume_ctx.get("has_context", False),
            "user_skills": skills,
            "full_resume": resume_ctx.get("full_resume", ""),
            "relevant_sections": resume_ctx.get("relevant_sections", ""),
            "market_demand_jobs": relevant_jobs,
            "application_history": "\n".join(trajectory) if trajectory else "No applications submitted yet.",
            "resume_context": resume_ctx
        }
