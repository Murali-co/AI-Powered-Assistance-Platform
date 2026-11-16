import logging
import traceback
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query, Request
from typing import Dict, Any, List, Optional
from starlette.concurrency import run_in_threadpool
from datetime import datetime
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.models.schemas import (
    JobFilterCriteria, JobOut, JobListResponse
)
from app.jobs.scraper import JobScraper
from app.jobs.filter import JobFilter
from app.jobs.matcher import JobMatcher
from app.jobs.repository import list_live_jobs
from app.utils.bg_jobs import create_job, update_job, get_job
from app.utils.job_queue import enqueue, run_job
from app.services.email_service import EmailService
from app.utils.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

async def notify_live_matches(user_id: int, jobs: List[Dict[str, Any]], hours_old: int):
    """Keep match alerts independent of whether the live listings can be shown."""
    try:
        from app.vector_db.profile_store import ProfileStore
        profile = await run_in_threadpool(ProfileStore.get_profile, user_id)
        if not profile or not profile.get('resume_text'):
            return
        matches = await run_in_threadpool(JobMatcher.match_jobs_for_user, user_id, limit=min(len(jobs), 50), hours_old=hours_old)
        new_ids = {job['id'] for job in jobs}
        high_matches = [job for job in matches if job.get('id') in new_ids and (job.get('match_score') or 0) >= 80]
        for job in high_matches[:5]:
            await run_in_threadpool(DBManager.add_notification, user_id=user_id, title='New Job Match Found',
                message=f"'{job['title']}' at '{job['company']}' matches {job['match_score']:.0f}% of your profile", type='job_alert')
    except Exception:
        logger.warning('Live listings were saved, but optional match alerts could not be generated.')


async def run_manual_fetch_task(job_id: str, user_id: int, title: str, location: str, hours_old: int = 168):
    """Store dated live listings before optional semantic matching."""
    try:
        update_job(job_id, "processing")
        jobs = await run_in_threadpool(JobScraper.scrape, search_term=title,
            location=location, results_wanted=30, hours_old=hours_old)
        if jobs:
            # Canonical Neon records remain available if the derived index fails.
            from app.jobs.repository import persist_live_jobs
            await run_in_threadpool(persist_live_jobs, jobs)
            await run_in_threadpool(JobMatcher.upsert_jobs, jobs)
        await run_in_threadpool(JobMatcher.reconcile_live_index, hours_old, title=title)
        completed = update_job(job_id, "completed", result={
            "count": len(jobs), "saved_count": len(jobs),
            "jobs_preview": [job["title"] for job in jobs[:5]],
            "message": "Live search completed." if jobs else "No dated live listings returned. Try another location or posting window."
        })
        if jobs and completed:
            await notify_live_matches(user_id, jobs, hours_old)
    except __import__('asyncio').CancelledError:
        raise
    except Exception:
        logger.exception("Live search failed for task %s", job_id)
        update_job(job_id, "failed", error="Live job search failed. Check source availability and backend services.")


@router.get("/fetch")
@limiter.limit("15/minute")
async def trigger_fetch(
    request: Request,
    background_tasks: BackgroundTasks,
    title: Optional[str] = Query(None, max_length=200, description="Job title keyword to search"),
    location: Optional[str] = Query(None, max_length=200, description="Location to search"),
    hours_old: Optional[int] = Query(None, ge=1, le=720, description="Max job age in hours"),
    job_type: Optional[str] = Query(None, description="Optional job type filter (remote, hybrid, onsite)"),
    current_user: dict = Depends(get_current_user)
):
    # Retrieve user's criteria if not specified in query
    user_id = current_user["id"]
    criteria = DBManager.get_criteria(user_id)
    
    default_title = "Software Engineer"
    if criteria and criteria.get("title"):
        default_title = criteria["title"]
    fetch_title = (title or default_title).strip()
    fetch_loc = (location or (criteria["location"] if criteria and criteria.get("location") else "Any")).strip()
    if not fetch_title or not fetch_loc:
        raise HTTPException(422, 'Search title and location must not be blank.')
    fetch_hours = hours_old or ((criteria or {}).get('hours_old') or 168)
    
    # Save/update user criteria if we got query params
    if title or location or job_type is not None:
        DBManager.save_criteria(
            user_id=user_id,
            title=fetch_title,
            location=fetch_loc,
            is_remote=(fetch_loc == "Remote"),
            job_type=job_type,
            hours_old=fetch_hours
        )
        
    job_id = await run_in_threadpool(enqueue, user_id, 'live_search',
        {'title': fetch_title, 'location': fetch_loc, 'hours_old': fetch_hours})
    background_tasks.add_task(run_job, job_id)
    
    return {"job_id": job_id, "status": "pending"}

@router.get("/{job_id}/status")
def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Background task ID not found."
        )
    job_user_id = job.get("user_id")
    if job_user_id != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Background task ID not found."
        )
    return job

@router.get("/list", response_model=JobListResponse)
async def list_jobs(
    hours_old: Optional[int] = Query(168, ge=1, le=720, description="Max job age in hours"),
    title: Optional[str] = Query(None, max_length=200),
    location: Optional[str] = Query(None, max_length=200),
    current_user: dict = Depends(get_current_user)
):
    criteria = dict(await run_in_threadpool(DBManager.get_criteria, current_user["id"]) or {})
    if title is not None:
        criteria["title"] = title
    if location is not None:
        criteria["location"] = location
        criteria["is_remote"] = location.lower() == "remote"
    jobs = await run_in_threadpool(list_live_jobs, hours_old or 168,
        title=criteria.get('title'), location=criteria.get('location'),
        is_remote=criteria.get('is_remote'), job_type=criteria.get('job_type'))
    jobs = JobFilter.filter_jobs(jobs, title=criteria.get("title"),
        location=criteria.get("location"), is_remote=criteria.get("is_remote"),
        job_type=criteria.get("job_type"), hours_old=hours_old or 168)
    return {"jobs": jobs}

@router.post("/match", response_model=JobListResponse)
async def match_jobs(
    hours_old: Optional[int] = Query(168, ge=1, le=720, description="Max job age in hours"),
    current_user: dict = Depends(get_current_user)
):
    effective_hours = hours_old
    matched = await run_in_threadpool(JobMatcher.match_jobs_for_user, user_id=current_user["id"], limit=50, hours_old=effective_hours)

    matched = JobFilter.live_jobs(matched, effective_hours or 168)
    # Apply filtering based on saved criteria if any
    criteria = await run_in_threadpool(DBManager.get_criteria, current_user["id"])
    if criteria:
        matched = JobFilter.filter_jobs(
            jobs=matched,
            title=criteria.get("title"),
            location=criteria.get("location"),
            is_remote=criteria.get("is_remote"),
            job_type=criteria.get("job_type"),
            hours_old=effective_hours or criteria.get("hours_old")
        )

    return {"jobs": [JobOut(**j) for j in matched]}

@router.post("/criteria")
def save_filter_criteria(
    criteria: JobFilterCriteria,
    current_user: dict = Depends(get_current_user)
):
    DBManager.save_criteria(
        user_id=current_user["id"],
        title=criteria.title,
        location=criteria.location,
        is_remote=criteria.is_remote,
        job_type=criteria.job_type,
        hours_old=criteria.hours_old or 168
    )
    return {"message": "Job filter criteria saved successfully."}

@router.get("/criteria")
def get_filter_criteria(current_user: dict = Depends(get_current_user)):
    criteria = DBManager.get_criteria(current_user["id"])
    if not criteria:
        return {"title": "", "location": "", "is_remote": None, "job_type": None, "hours_old": 168}
    return criteria

@router.get("/explain/{job_id}")
async def explain_job_match(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        explanation = await JobMatcher.explain_job_match(
            user_id=current_user["id"],
            job_id=job_id
        )
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        logger.exception(f"Failed to explain job match {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate job match explanation"
        )




