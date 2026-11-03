import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import func
from app.auth.utils import get_current_user
from app.db.session import SessionLocal
from app.db.models import (
    ResumeVersion, UserCriteria, InterviewSession, ApplicationHistory,
    VerifiedProfile, CareerMilestone, JobPosting, SavedJob
)
from app.vector_db.profile_store import ProfileStore
from app.services.esco_service import ESCOSkillService
from app.jobs.two_stage_matcher import TwoStageJobMatcher

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileCompletenessResponse(BaseModel):
    completion_score: int
    resume_uploaded: bool
    skills_filled: bool
    criteria_set: bool
    interview_practiced: bool
    applications_submitted: bool
    breakdown: dict

    class Config:
        from_attributes = True


class VerifiedProfileUpdateRequest(BaseModel):
    skills: List[str]
    work_experience: Optional[List[Dict[str, Any]]] = []
    education: Optional[List[Dict[str, Any]]] = []
    projects: Optional[List[Dict[str, Any]]] = []
    certifications: Optional[List[Dict[str, Any]]] = []
    consent_settings: Optional[Dict[str, Any]] = {"local_only": True, "external_ai": False}


class MilestoneStatusUpdateRequest(BaseModel):
    status: Optional[str] = None  # pending, in_progress, completed
    is_completed: Optional[bool] = None


@router.get("/completeness", response_model=ProfileCompletenessResponse)
async def get_profile_completeness(current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        user_id = current_user["id"]
        resume = db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).first()
        resume_uploaded = resume is not None

        skills_filled = resume_uploaded and len(resume.resume_text) > 200 if resume else False

        criteria = db.query(UserCriteria).filter(UserCriteria.user_id == user_id).first()
        criteria_set = criteria is not None and criteria.title is not None

        interview = db.query(InterviewSession).filter(
            InterviewSession.user_id == user_id,
            InterviewSession.is_finished == True
        ).first()
        interview_practiced = interview is not None

        application = db.query(ApplicationHistory).filter(ApplicationHistory.user_id == user_id).first()
        applications_submitted = application is not None

        score_parts = {
            "resume": 20 if resume_uploaded else 0,
            "skills": 20 if skills_filled else 0,
            "criteria": 20 if criteria_set else 0,
            "interview": 20 if interview_practiced else 0,
            "applications": 20 if applications_submitted else 0,
        }
        total_score = sum(score_parts.values())

        return {
            "completion_score": total_score,
            "resume_uploaded": resume_uploaded,
            "skills_filled": skills_filled,
            "criteria_set": criteria_set,
            "interview_practiced": interview_practiced,
            "applications_submitted": applications_submitted,
            "breakdown": score_parts
        }
    finally:
        db.close()


@router.get("/verified")
async def get_verified_profile(current_user: dict = Depends(get_current_user)):
    """
    Retrieves candidate's verified career facts and privacy consent boundaries.
    """
    user_id = current_user["id"]
    db = SessionLocal()
    try:
        vp = db.query(VerifiedProfile).filter(VerifiedProfile.user_id == user_id).first()
        if not vp:
            # Fallback to vector profile store to seed verified profile
            store_p = ProfileStore.get_profile(user_id) or {}
            skills = store_p.get("skills", [])
            return {
                "skills": skills,
                "work_experience": [],
                "education": [],
                "projects": [],
                "certifications": [],
                "consent_settings": {"local_only": True, "external_ai": False},
                "is_initialized": False
            }

        return {
            "skills": json.loads(vp.skills or "[]"),
            "work_experience": json.loads(vp.work_experience or "[]"),
            "education": json.loads(vp.education or "[]"),
            "projects": json.loads(vp.projects or "[]"),
            "certifications": json.loads(vp.certifications or "[]"),
            "consent_settings": json.loads(vp.consent_settings or '{"local_only": true, "external_ai": false}'),
            "updated_at": vp.updated_at.isoformat() if vp.updated_at else None,
            "is_initialized": True
        }
    finally:
        db.close()


@router.post("/verified")
@router.put("/verified")
async def save_verified_profile(
    req: VerifiedProfileUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Saves candidate confirmed factual profile data with ownership enforcement.
    """
    user_id = current_user["id"]
    db = SessionLocal()
    try:
        vp = db.query(VerifiedProfile).filter(VerifiedProfile.user_id == user_id).first()
        if not vp:
            vp = VerifiedProfile(
                user_id=user_id,
                skills=json.dumps(req.skills),
                work_experience=json.dumps(req.work_experience or []),
                education=json.dumps(req.education or []),
                projects=json.dumps(req.projects or []),
                certifications=json.dumps(req.certifications or []),
                consent_settings=json.dumps(req.consent_settings or {"local_only": True, "external_ai": False})
            )
            db.add(vp)
        else:
            vp.skills = json.dumps(req.skills)
            vp.work_experience = json.dumps(req.work_experience or [])
            vp.education = json.dumps(req.education or [])
            vp.projects = json.dumps(req.projects or [])
            vp.certifications = json.dumps(req.certifications or [])
            if req.consent_settings:
                vp.consent_settings = json.dumps(req.consent_settings)

        db.commit()

        # Update in-memory / vector profile store as well
        ProfileStore.store_profile(
            user_id=user_id,
            resume_text=ProfileStore.get_profile(user_id).get("resume_text", "") if ProfileStore.get_profile(user_id) else "",
            skills=req.skills
        )

        return {"message": "Verified career profile updated successfully.", "skills_count": len(req.skills)}
    finally:
        db.close()


@router.get("/roadmap")
async def get_career_roadmap(
    target_role: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Converts identified skill gaps into a structured, practical learning plan with verifiable resources.
    """
    user_id = current_user["id"]
    db = SessionLocal()
    try:
        role = target_role or "Full Stack Software Engineer"
        # 1. Fetch existing milestones from database
        milestones = db.query(CareerMilestone).filter(
            CareerMilestone.user_id == user_id,
            CareerMilestone.target_role == role
        ).all()

        if milestones:
            return {
                "target_role": role,
                "milestones": [
                    {
                        "id": m.id,
                        "skill_name": m.skill_name,
                        "importance": m.importance,
                        "current_proficiency": m.current_proficiency,
                        "target_proficiency": m.target_proficiency,
                        "resources": json.loads(m.resources or "[]"),
                        "exercises": json.loads(m.exercises or "[]"),
                        "status": m.status
                    }
                    for m in milestones
                ]
            }

        # 2. If no milestones exist for this role, generate initial roadmap from ESCO & user skills
        user_skills = []
        vp = db.query(VerifiedProfile).filter(VerifiedProfile.user_id == user_id).first()
        if vp:
            user_skills = json.loads(vp.skills or "[]")
        else:
            p = ProfileStore.get_profile(user_id) or {}
            user_skills = p.get("skills", [])

        # Essential curriculum mapping with verifiable links
        role_curriculum = [
            {
                "skill": "Docker & Containerization",
                "importance": "core",
                "curr": "beginner" if "Docker" not in user_skills else "proficient",
                "target": "proficient",
                "resources": [
                    {"name": "Docker Official Documentation", "url": "https://docs.docker.com/get-started/"},
                    {"name": "Container Best Practices", "url": "https://docs.docker.com/develop/develop-images/guidelines/"}
                ],
                "exercises": [
                    "Write a multi-stage Dockerfile for a FastAPI backend and optimize image size under 150MB.",
                    "Configure Docker Compose with PostgreSQL database health checks."
                ]
            },
            {
                "skill": "PostgreSQL & Database Optimization",
                "importance": "core",
                "curr": "intermediate" if "PostgreSQL" in user_skills else "beginner",
                "target": "proficient",
                "resources": [
                    {"name": "PostgreSQL Official Documentation", "url": "https://www.postgresql.org/docs/current/"},
                    {"name": "Use The Index, Luke (SQL Indexing)", "url": "https://use-the-index-luke.com/"}
                ],
                "exercises": [
                    "Analyze EXPLAIN ANALYZE queries on tables with 100k+ rows and add composite indexes.",
                    "Write Alembic transactional migration scripts with safe rollbacks."
                ]
            },
            {
                "skill": "FastAPI & Asynchronous Architecture",
                "importance": "core",
                "curr": "intermediate" if "FastAPI" in user_skills else "beginner",
                "target": "advanced",
                "resources": [
                    {"name": "FastAPI Official Tutorial", "url": "https://fastapi.tiangolo.com/tutorial/"},
                    {"name": "Python asyncio Documentation", "url": "https://docs.python.org/3/library/asyncio.html"}
                ],
                "exercises": [
                    "Implement double-submit CSRF and strict Content Security Policy middleware.",
                    "Build an asynchronous background worker using asyncio tasks with graceful shutdown."
                ]
            },
            {
                "skill": "System Design & Microservices Architecture",
                "importance": "advanced",
                "curr": "beginner",
                "target": "proficient",
                "resources": [
                    {"name": "System Design Primer", "url": "https://github.com/donnemartin/system-design-primer"},
                    {"name": "Designing Data-Intensive Applications", "url": "https://dataintensive.net/"}
                ],
                "exercises": [
                    "Design an end-to-end event-driven notification architecture with idempotent consumers.",
                    "Implement distributed rate limiting using sliding window algorithms."
                ]
            }
        ]

        created_milestones = []
        for item in role_curriculum:
            cm = CareerMilestone(
                user_id=user_id,
                target_role=role,
                skill_name=item["skill"],
                importance=item["importance"],
                current_proficiency=item["curr"],
                target_proficiency=item["target"],
                resources=json.dumps(item["resources"]),
                exercises=json.dumps(item["exercises"]),
                status="completed" if item["curr"] == "proficient" else "pending"
            )
            db.add(cm)
            created_milestones.append(cm)

        db.commit()

        return {
            "target_role": role,
            "milestones": [
                {
                    "id": m.id,
                    "skill_name": m.skill_name,
                    "importance": m.importance,
                    "current_proficiency": m.current_proficiency,
                    "target_proficiency": m.target_proficiency,
                    "resources": json.loads(m.resources or "[]"),
                    "exercises": json.loads(m.exercises or "[]"),
                    "status": m.status,
                    "is_completed": m.status == "completed"
                }
                for m in created_milestones
            ]
        }
    finally:
        db.close()


@router.post("/roadmap/milestones/{milestone_id}")
@router.patch("/roadmap/milestones/{milestone_id}")
async def update_milestone_status(
    milestone_id: int,
    req: MilestoneStatusUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Updates completion status of a specific career roadmap milestone.
    Enforces user ownership.
    """
    db = SessionLocal()
    try:
        user_id = current_user["id"]
        milestone = db.query(CareerMilestone).filter(
            CareerMilestone.id == milestone_id,
            CareerMilestone.user_id == user_id
        ).first()

        if not milestone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Milestone not found or access denied."
            )

        target_status = req.status
        if target_status is None and req.is_completed is not None:
            target_status = "completed" if req.is_completed else "pending"

        if target_status not in ["pending", "in_progress", "completed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status. Must be pending, in_progress, or completed."
            )

        milestone.status = target_status
        db.commit()
        return {
            "message": "Milestone status updated.",
            "milestone_id": milestone_id,
            "status": target_status,
            "is_completed": target_status == "completed"
        }
    finally:
        db.close()


def _fetch_dashboard_data(user_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        # 1. Profile and verified skills (L3: select skills column only)
        vp = db.query(VerifiedProfile.skills).filter(VerifiedProfile.user_id == user_id).first()
        verified_skills = json.loads(vp[0]) if vp and vp[0] else []
        if not verified_skills:
            p_data = ProfileStore.get_profile(user_id) or {}
            verified_skills = p_data.get("skills", [])

        # 2. Resume Versions (L3: select only metadata, avoiding large resume_text blobs)
        versions = (
            db.query(
                ResumeVersion.id,
                ResumeVersion.version_label,
                ResumeVersion.target_role,
                ResumeVersion.created_at,
            )
            .filter(ResumeVersion.user_id == user_id)
            .order_by(ResumeVersion.created_at.desc())
            .all()
        )
        versions_summary = [
            {
                "id": v[0],
                "label": v[1],
                "target_role": v[2] or "General",
                "created_at": v[3].isoformat() if v[3] else None
            }
            for v in versions
        ]

        # 3. Application Pipeline (L3: select only status)
        app_statuses = db.query(ApplicationHistory.status).filter(ApplicationHistory.user_id == user_id).all()
        app_status_counts = {"applied": 0, "interview_scheduled": 0, "offered": 0, "rejected": 0}
        for (st_val,) in app_statuses:
            st = (st_val or "applied").lower()
            if st in app_status_counts:
                app_status_counts[st] += 1
            else:
                app_status_counts["applied"] += 1

        # 4. Saved Jobs
        saved_jobs_count = db.query(func.count(SavedJob.id)).filter(SavedJob.user_id == user_id).scalar() or 0

        # 5. Interview Practice (L3: select required columns only)
        interviews = (
            db.query(
                InterviewSession.id,
                InterviewSession.is_finished,
                InterviewSession.score,
                InterviewSession.difficulty_level,
                InterviewSession.topics_covered,
                InterviewSession.created_at,
            )
            .filter(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.created_at.desc())
            .all()
        )
        completed_interviews = [i for i in interviews if i[1]]
        latest_interview = completed_interviews[0] if completed_interviews else (interviews[0] if interviews else None)

        interview_stats = {
            "total_sessions": len(interviews),
            "completed_sessions": len(completed_interviews),
            "latest_score": latest_interview[2] if latest_interview else None,
            "current_difficulty": latest_interview[3] if latest_interview else 3,
            "topics_covered_count": len(json.loads(latest_interview[4] or "[]")) if latest_interview else 0
        }

        # 6. Career Roadmap (L3: select status only)
        milestones = db.query(CareerMilestone.status).filter(CareerMilestone.user_id == user_id).all()
        roadmap_stats = {
            "total_milestones": len(milestones),
            "completed": sum(1 for (m_stat,) in milestones if m_stat == "completed"),
            "in_progress": sum(1 for (m_stat,) in milestones if m_stat == "in_progress"),
            "pending": sum(1 for (m_stat,) in milestones if m_stat == "pending")
        }

        # 7. Match sample with verified active jobs (L3: select only required columns)
        active_jobs = (
            db.query(
                JobPosting.id,
                JobPosting.title,
                JobPosting.company,
                JobPosting.location,
                JobPosting.required_skills,
                JobPosting.preferred_skills,
                JobPosting.last_verified_at,
            )
            .filter(JobPosting.is_active == True)
            .limit(5)
            .all()
        )
        recommended_jobs = []
        for j in active_jobs:
            req_s = json.loads(j[4] or "[]")
            pref_s = json.loads(j[5] or "[]")
            esco_eval = ESCOSkillService.analyze_skill_overlap(verified_skills, req_s, pref_s)
            recommended_jobs.append({
                "id": j[0],
                "title": j[1],
                "company": j[2],
                "location": j[3],
                "match_score": int(esco_eval["adjusted_overlap_score"] * 100),
                "matched_skills": esco_eval["matched_skills"],
                "missing_skills": esco_eval["missing_skills"],
                "transferable_skills": [t["candidate_skill"] for t in esco_eval["transferable_skills"]],
                "last_verified_at": j[6].isoformat() if j[6] else None
            })

        return {
            "profile": {
                "skills_count": len(verified_skills),
                "verified_skills": verified_skills[:12],
                "resume_versions_count": len(versions)
            },
            "recommended_jobs": recommended_jobs,
            "saved_jobs_count": saved_jobs_count,
            "application_pipeline": app_status_counts,
            "interview_stats": interview_stats,
            "roadmap_stats": roadmap_stats,
            "resume_versions": versions_summary
        }
    finally:
        db.close()


@router.get("/overview")
async def get_dashboard_overview(current_user: dict = Depends(get_current_user)):
    """
    Real authenticated dashboard data aggregation:
    - Recommended jobs with match scores and ESCO explanations
    - Profile completeness and verified skills
    - Saved jobs pipeline and application status counts
    - Interview practice stats (difficulty level, latest score, sessions count)
    - Career roadmap milestones progress
    """
    user_id = current_user["id"]
    data = await run_in_threadpool(_fetch_dashboard_data, user_id)
    return {
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "full_name": current_user["full_name"]
        },
        **data
    }
