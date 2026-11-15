"""
PostgreSQL-backed Background Job Lifecycle Manager for AI Powered Assistance Platform.

Replaces process-local-only memory state with database-backed persistence:
- Unique UUID job IDs
- Authenticated user ownership tracking
- Explicit status transitions (pending -> processing -> completed / failed / cancelled)
- High-precision timestamps (created_at, started_at, completed_at, expires_at)
- Safe, sanitized error storage
- Multi-worker-safe job claiming using row locking (FOR UPDATE SKIP LOCKED on PostgreSQL)
- Crash recovery for stale/orphaned running tasks upon server restart
- Periodic TTL expiration and bounded storage cleanup
- Object-level authorization helper to prevent cross-user IDOR
"""
import uuid
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import BackgroundJob

logger = logging.getLogger(__name__)

# In-memory dictionary mirror for backwards compatibility with tests and fast local reads
jobs_lock = threading.Lock()
jobs_db: Dict[str, Dict[str, Any]] = {}

VALID_STATUSES = {"pending", "processing", "completed", "failed", "cancelled"}


def _sanitize_error(error: Optional[Any]) -> Optional[str]:
    """Sanitize and boundedly truncate error messages for safe persistence."""
    if error is None:
        return None
    err_str = str(error).strip()
    # Mask any potential database connection strings or tokens if present
    for secret_marker in ("postgres://", "postgresql://", "Bearer ", "password="):
        if secret_marker in err_str:
            err_str = err_str.split(secret_marker)[0] + "[REDACTED_CREDENTIAL]"
    return err_str[:1000]


def create_job(
    user_id: Optional[int] = None,
    job_type: Optional[str] = None,
    ttl_hours: int = 24
) -> str:
    """
    Create and persist a new background job record with authenticated ownership.
    Returns the unique UUID string.
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)

    db: Session = SessionLocal()
    try:
        job = BackgroundJob(
            id=job_id,
            user_id=user_id,
            job_type=job_type,
            status="pending",
            created_at=now,
            expires_at=expires
        )
        db.add(job)
        db.commit()
    except Exception as e:
        logger.error("Failed to persist background job %s to database: %s", job_id, e)
        db.rollback()
    finally:
        db.close()

    # Mirror to in-memory store for fast read and test compatibility
    with jobs_lock:
        jobs_db[job_id] = {
            "id": job_id,
            "status": "pending",
            "result": None,
            "error": None,
            "user_id": user_id,
            "job_type": job_type,
            "created_at": now.isoformat(),
            "started_at": None,
            "completed_at": None,
            "expires_at": expires.isoformat()
        }

    return job_id


def update_job(
    job_id: str,
    status: str,
    result: Any = None,
    error: Optional[Any] = None
) -> bool:
    """
    Transition job status with timestamps and error/result metadata.
    """
    clean_status = status.lower().strip()
    if clean_status not in VALID_STATUSES:
        logger.warning("Invalid job status '%s' requested for job %s.", status, job_id)
        clean_status = "failed"
        if not error:
            error = f"Invalid status transition to {status}"

    safe_err = _sanitize_error(error)
    now = datetime.now(timezone.utc)

    db: Session = SessionLocal()
    updated = False
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.status = clean_status
            if clean_status == "processing" and not job.started_at:
                job.started_at = now
            elif clean_status in ("completed", "failed", "cancelled"):
                job.completed_at = now

            if result is not None:
                job.result = result
            if safe_err is not None:
                job.error = safe_err

            db.commit()
            updated = True
        else:
            logger.warning("Background job %s not found in database during update.", job_id)
    except Exception as e:
        logger.error("Error updating background job %s: %s", job_id, e)
        db.rollback()
    finally:
        db.close()

    # Update in-memory mirror
    with jobs_lock:
        if job_id in jobs_db:
            jobs_db[job_id]["status"] = clean_status
            if clean_status == "processing" and not jobs_db[job_id].get("started_at"):
                jobs_db[job_id]["started_at"] = now.isoformat()
            elif clean_status in ("completed", "failed", "cancelled"):
                jobs_db[job_id]["completed_at"] = now.isoformat()
            if result is not None:
                jobs_db[job_id]["result"] = result
            if safe_err is not None:
                jobs_db[job_id]["error"] = safe_err
        else:
            jobs_db[job_id] = {
                "id": job_id,
                "status": clean_status,
                "result": result,
                "error": safe_err,
                "completed_at": now.isoformat() if clean_status in ("completed", "failed") else None
            }

    return updated


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch background job status and result. Returns dictionary matching API contract.
    """
    db: Session = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            return {
                "id": job.id,
                "job_id": job.id,
                "status": job.status,
                "result": job.result,
                "error": job.error,
                "user_id": job.user_id,
                "job_type": job.job_type,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "expires_at": job.expires_at.isoformat() if job.expires_at else None
            }
        return None
    except Exception as e:
        logger.error("Error reading background job %s from database: %s", job_id, e)
        with jobs_lock:
            return jobs_db.get(job_id)
    finally:
        db.close()


def get_user_job(job_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch background job verifying that the requesting user owns the job.
    Returns None if job does not exist or belongs to another user.
    """
    job = get_job(job_id)
    if not job:
        return None
    owner_id = job.get("user_id")
    if owner_id is not None and owner_id != user_id:
        return None
    return job


def claim_next_job(worker_id: str, job_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    Multi-worker-safe job claiming using PostgreSQL row locking:
    SELECT FOR UPDATE SKIP LOCKED ensures only one worker claims a job.
    Falls back gracefully on SQLite.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        query = db.query(BackgroundJob).filter(BackgroundJob.status == "pending")
        if job_types:
            query = query.filter(BackgroundJob.job_type.in_(job_types))

        # Check if database supports FOR UPDATE SKIP LOCKED (PostgreSQL)
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            job = query.order_by(BackgroundJob.created_at.asc()).with_for_update(skip_locked=True).first()
        else:
            job = query.order_by(BackgroundJob.created_at.asc()).first()

        if not job:
            return None

        job.status = "processing"
        job.worker_id = worker_id
        job.claimed_at = now
        job.started_at = now
        db.commit()

        job_dict = {
            "id": job.id,
            "job_id": job.id,
            "user_id": job.user_id,
            "job_type": job.job_type,
            "status": "processing",
            "started_at": now.isoformat()
        }
        with jobs_lock:
            if job.id in jobs_db:
                jobs_db[job.id]["status"] = "processing"
                jobs_db[job.id]["started_at"] = now.isoformat()
        return job_dict
    except Exception as e:
        logger.error("Error claiming next background job: %s", e)
        db.rollback()
        return None
    finally:
        db.close()


def recover_pending_or_stale_jobs(stale_minutes: int = 30) -> int:
    """
    Recover or mark failed any jobs that were abandoned in 'processing' state
    due to worker crashes or server restarts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    now = datetime.now(timezone.utc)
    recovered = 0

    db: Session = SessionLocal()
    try:
        stale_jobs = db.query(BackgroundJob).filter(
            BackgroundJob.status == "processing",
            or_(
                BackgroundJob.started_at < cutoff,
                and_(BackgroundJob.started_at.is_(None), BackgroundJob.created_at < cutoff)
            )
        ).all()

        for j in stale_jobs:
            j.status = "failed"
            j.error = f"Task timed out or was interrupted by worker restart (stale > {stale_minutes}m)."
            j.completed_at = now
            recovered += 1

        if recovered > 0:
            db.commit()
            logger.info("Recovered %d stale background jobs after server restart.", recovered)
    except Exception as e:
        logger.error("Error recovering stale background jobs: %s", e)
        db.rollback()
    finally:
        db.close()

    return recovered


def cleanup_expired_jobs(max_retention_days: int = 7) -> int:
    """
    Delete expired background job records to bound storage size.
    Purges jobs whose expires_at is passed or completed jobs older than max_retention_days.
    """
    now = datetime.now(timezone.utc)
    retention_cutoff = now - timedelta(days=max_retention_days)
    purged = 0

    db: Session = SessionLocal()
    try:
        expired_ids = [r[0] for r in db.query(BackgroundJob.id).filter(
            or_(
                and_(BackgroundJob.expires_at.is_not(None), BackgroundJob.expires_at < now),
                and_(BackgroundJob.completed_at.is_not(None), BackgroundJob.completed_at < retention_cutoff)
            )
        ).all()]
        if expired_ids:
            purged = db.query(BackgroundJob).filter(BackgroundJob.id.in_(expired_ids)).delete(synchronize_session=False)
            db.commit()
            with jobs_lock:
                for eid in expired_ids:
                    jobs_db.pop(eid, None)
            logger.info("Purged %d expired background job records.", purged)
    except Exception as e:
        logger.error("Error cleaning up expired background jobs: %s", e)
        db.rollback()
    finally:
        db.close()

    return purged
