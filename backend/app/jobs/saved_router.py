from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Optional
from app.db.models import SavedJob
from app.db.session import SessionLocal
from app.auth.utils import get_current_user
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone

router = APIRouter(prefix="/jobs/saved", tags=["saved-jobs"])

class SaveJobRequest(BaseModel):
    job_id: str
    job_title: str
    company: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    notes: Optional[str] = None
    stage: str = "saved"

class UpdateStageRequest(BaseModel):
    stage: str

class UpdateNotesRequest(BaseModel):
    notes: str

class SavedJobResponse(BaseModel):
    id: int
    job_id: str
    job_title: str
    company: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    notes: Optional[str] = None
    stage: str = "saved"
    saved_at: datetime

    model_config = ConfigDict(from_attributes=True)

@router.post("", response_model=SavedJobResponse)
@router.post("/save", response_model=SavedJobResponse)
async def save_job(
    req: SaveJobRequest,
    current_user: dict = Depends(get_current_user)
):
    """Save a job to watchlist"""
    db = SessionLocal()
    try:
        # Check if already saved
        existing = db.query(SavedJob).filter(
            SavedJob.user_id == current_user["id"],
            SavedJob.job_id == req.job_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job already saved"
            )
        
        # Add new saved job
        saved_job = SavedJob(
            user_id=current_user["id"],
            job_id=req.job_id,
            job_title=req.job_title,
            company=req.company,
            location=req.location,
            job_url=req.job_url,
            notes=req.notes,
            stage=req.stage or "saved"
        )
        db.add(saved_job)
        db.commit()
        db.refresh(saved_job)
        return saved_job
    finally:
        db.close()

@router.get("", response_model=List[SavedJobResponse])
@router.get("/list", response_model=List[SavedJobResponse])
async def get_saved_jobs(
    current_user: dict = Depends(get_current_user)
):
    """Get all saved jobs for current user"""
    db = SessionLocal()
    try:
        saved_jobs = db.query(SavedJob).filter(
            SavedJob.user_id == current_user["id"]
        ).order_by(SavedJob.saved_at.desc()).all()
        return saved_jobs
    finally:
        db.close()

@router.delete("/{saved_job_id}")
async def remove_saved_job(
    saved_job_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Remove a job from watchlist"""
    db = SessionLocal()
    try:
        saved_job = db.query(SavedJob).filter(
            SavedJob.id == saved_job_id,
            SavedJob.user_id == current_user["id"]
        ).first()
        
        if not saved_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved job not found"
            )
        
        db.delete(saved_job)
        db.commit()
        return {"message": "Saved job removed"}
    finally:
        db.close()

@router.patch("/{saved_job_id}/stage")
async def update_saved_job_stage(
    saved_job_id: int,
    stage: Optional[str] = None,
    payload: Optional[UpdateStageRequest] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    target_stage = stage or (payload.stage if payload else None)
    if not target_stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stage must be provided via query parameter or JSON body."
        )

    db = SessionLocal()
    try:
        saved_job = db.query(SavedJob).filter(
            SavedJob.id == saved_job_id,
            SavedJob.user_id == current_user["id"]
        ).first()
        if not saved_job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved job not found")
        saved_job.stage = target_stage
        db.commit()
        db.refresh(saved_job)
        return saved_job
    finally:
        db.close()

@router.patch("/{saved_job_id}/notes")
async def update_saved_job_notes(
    saved_job_id: int,
    notes: Optional[str] = None,
    payload: Optional[UpdateNotesRequest] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """Update notes for a saved job"""
    target_notes = notes if notes is not None else (payload.notes if payload else "")

    db = SessionLocal()
    try:
        saved_job = db.query(SavedJob).filter(
            SavedJob.id == saved_job_id,
            SavedJob.user_id == current_user["id"]
        ).first()
        
        if not saved_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved job not found"
            )
        
        saved_job.notes = target_notes
        db.commit()
        db.refresh(saved_job)
        return saved_job
    finally:
        db.close()
