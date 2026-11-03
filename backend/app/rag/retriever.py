from typing import List, Dict, Any, Optional
import json
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.auth.models import DBManager
from app.vector_db.embedder import embed_text

class RAGRetriever:
    @classmethod
    def get_resume_context(cls, user_id: int, query: str) -> Dict[str, Any]:
        """
        Retrieves user resume text, skills, and semantically matching resume sections.
        """
        profile = ProfileStore.get_profile(user_id) or {}
        skills = profile.get("skills", [])
        resume_text = profile.get("resume_text", "")
        
        # Get granular resume sections matching the query
        matching_sections = ProfileStore.query_profile_sections(user_id, query, n_results=3)
        sections_context = "\n\n".join([
            f"--- Section: {item['metadata'].get('section_name', 'Experience')} ---\n{item['document']}"
            for item in matching_sections
        ])

        return {
            "skills": skills,
            "full_resume": resume_text,
            "relevant_sections": sections_context,
            "raw_sections": matching_sections
        }

    @classmethod
    def get_job_context(cls, user_id: int, job_id: str) -> Dict[str, Any]:
        """
        Retrieves target job details, match metrics, missing skills, and relevant user sections.
        """
        # Find the specific job match info (scores, missing skills, description)
        all_matches = JobMatcher.match_jobs_for_user(user_id)
        job_match = next((j for j in all_matches if j["id"] == job_id), None)
        
        if not job_match:
            # Fallback direct retrieve from ChromaDB if not in matched list
            collection = JobMatcher.get_collection()
            result = collection.get(ids=[job_id])
            if result and result["ids"]:
                job_match = {
                    "id": job_id,
                    "title": result["metadatas"][0].get("title", "Unknown Role"),
                    "company": result["metadatas"][0].get("company", "Unknown Company"),
                    "description": result["documents"][0],
                    "match_score": 0.0,
                    "matched_skills": [],
                    "missing_skills": []
                }
            else:
                return {}

        # Ensure job_match has required fields before accessing
        if not job_match or "description" not in job_match:
            return {}

        # Query user resume sections matching the job description to find relevant background
        matching_sections = ProfileStore.query_profile_sections(user_id, job_match["description"], n_results=3)
        sections_context = "\n\n".join([
            f"--- Resume section relevant to job: {item['metadata'].get('section_name', 'Experience')} ---\n{item['document']}"
            for item in matching_sections
        ])

        return {
            "job": job_match,
            "relevant_resume_sections": sections_context
        }

    @classmethod
    def get_career_context(cls, user_id: int, query: str) -> Dict[str, Any]:
        """
        Retrieves user profile and searches active job listings semantically 
        to ground career guidance in actual market demands.
        """
        profile = ProfileStore.get_profile(user_id) or {}
        skills = profile.get("skills", [])
        
        # Search job_listings semantically for roles matching the query
        collection = JobMatcher.get_collection()
        total_jobs = collection.count()
        results = None
        if total_jobs > 0:
            effective_n_results = min(3, total_jobs)
            query_emb = embed_text(query)
            results = collection.query(
                query_embeddings=[query_emb],
                n_results=effective_n_results
            )

        relevant_jobs = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                relevant_jobs.append({
                    "title": results["metadatas"][0][i].get("title", "Unknown"),
                    "company": results["metadatas"][0][i].get("company", "Unknown"),
                    "description": results["documents"][0][i]
                })

        # Fetch user's actual applications history to check their current trajectory
        applications = DBManager.get_applications(user_id)
        trajectory = [
            f"Applied to {app['job_title']} at {app['company']} (Status: {app['status']})"
            for app in applications[:5]  # last 5 applications
        ]

        return {
            "user_skills": skills,
            "market_demand_jobs": relevant_jobs,
            "application_history": "\n".join(trajectory) if trajectory else "No applications submitted yet."
        }
