"""Neon-backed dispatch for retryable searches and local AI drafts.

The existing JSON result column holds a versioned request envelope until the
job finishes. No schema change or external queue is required. Only the fixed
operations below can run; none submits an application or sends an email.
Execution is at least once after process loss, with fenced results and a
bounded retry count. Public status responses hide the internal envelope.
"""
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from sqlalchemy import and_, or_, update
from sqlalchemy.dialects.postgresql import insert
from starlette.concurrency import run_in_threadpool

from app.db.models import BackgroundJob
from app.db.session import SessionLocal
from app.utils.bg_jobs import active_worker, update_job

logger = logging.getLogger(__name__)
OPERATIONS = ('live_search', 'role_search', 'resume_analysis', 'application_draft')
LEASE_SECONDS = 90
MAX_ATTEMPTS = 3


class Search(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    location: str = Field(default='Any', min_length=1, max_length=200)
    hours_old: int = Field(default=168, ge=1, le=720)


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    target_role: str = Field(min_length=1, max_length=200)


class Draft(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    job_id: str = Field(min_length=1, max_length=200)


def is_envelope(result):
    return isinstance(result, dict) and result.get('_dispatch_version') == 1


def can_retry(result):
    return (is_envelope(result) and type(result.get('attempts')) is int
            and 0 <= result['attempts'] < MAX_ATTEMPTS and isinstance(result.get('input'), dict))


def enqueue(user_id: int, operation: Literal['live_search', 'role_search', 'resume_analysis', 'application_draft'], payload: dict, job_id=None):
    schema = {'live_search': Search, 'role_search': Search, 'resume_analysis': Analysis, 'application_draft': Draft}.get(operation)
    if schema is None or type(user_id) is not int or user_id <= 0:
        raise ValueError('Unsupported queue operation or owner.')
    data = schema.model_validate(payload).model_dump()
    identifier = str(uuid.UUID(job_id)) if job_id else str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    envelope = {'_dispatch_version': 1, 'input': data, 'attempts': 0}
    try:
        with SessionLocal.begin() as db:
            # Deterministic internal child IDs make parent crash retries idempotent.
            db.execute(insert(BackgroundJob).values(id=identifier, user_id=user_id,
                job_type=operation, status='pending', result=envelope,
                created_at=now, expires_at=now + timedelta(hours=24))
                .on_conflict_do_nothing(index_elements=['id']))
            existing = db.get(BackgroundJob, identifier)
            if existing.user_id != user_id or existing.job_type != operation:
                raise ValueError('Queue request does not match the existing owner or operation.')
    except Exception as error:
        logger.warning('Queue request could not be saved (%s).', type(error).__name__)
        raise HTTPException(503, 'Background task storage is unavailable. No new task was accepted.') from None
    return identifier


def claim(job_id=None):
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as db:
        query = db.query(BackgroundJob).filter(BackgroundJob.status == 'pending',
            BackgroundJob.job_type.in_(OPERATIONS),
            or_(BackgroundJob.expires_at.is_(None), BackgroundJob.expires_at > now))
        if job_id is not None:
            query = query.filter(BackgroundJob.id == job_id)
        job = query.order_by(BackgroundJob.created_at).with_for_update(skip_locked=True).first()
        if job is None:
            return None
        envelope = job.result
        if not can_retry(envelope):
            job.status, job.completed_at = 'failed', now
            job.error = 'The saved task cannot be dispatched safely. Start a new request.'
            return None
        job.result = {**envelope, 'attempts': envelope.get('attempts', 0) + 1}
        job.worker_id = str(uuid.uuid4())
        job.claimed_at = now
        job.started_at = job.started_at or now
        job.status = 'processing'
        return {'id': job.id, 'user_id': job.user_id, 'operation': job.job_type,
                'worker_id': job.worker_id, 'input': envelope['input']}


def heartbeat(job_id, worker_id):
    with SessionLocal.begin() as db:
        result = db.execute(update(BackgroundJob).where(BackgroundJob.id == job_id,
            BackgroundJob.worker_id == worker_id, BackgroundJob.status == 'processing')
            .values(claimed_at=datetime.now(timezone.utc)))
        return result.rowcount == 1


def release(job_id, worker_id):
    """Requeue only the current lease, preserving a completed or cancelled result."""
    with SessionLocal.begin() as db:
        job = db.query(BackgroundJob).filter_by(id=job_id, worker_id=worker_id,
            status='processing').with_for_update().first()
        if job is None:
            return False
        if can_retry(job.result):
            job.status, job.worker_id, job.claimed_at = 'pending', None, None
        else:
            job.status = 'failed'
            job.completed_at = datetime.now(timezone.utc)
            job.error = 'Task interrupted repeatedly. Start a new request.'
        return True


def recover_expired_leases():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=LEASE_SECONDS)
    recovered = 0
    with SessionLocal.begin() as db:
        jobs = db.query(BackgroundJob).filter(BackgroundJob.job_type.in_(OPERATIONS),
            BackgroundJob.status.in_(['pending', 'processing']),
            or_(BackgroundJob.expires_at <= now, and_(BackgroundJob.status == 'processing',
                or_(BackgroundJob.claimed_at.is_(None), BackgroundJob.claimed_at < cutoff))))
        jobs = jobs.order_by(BackgroundJob.created_at).limit(100).with_for_update(skip_locked=True).all()
        for job in jobs:
            if job.expires_at is not None and job.expires_at <= now:
                job.status, job.completed_at = 'failed', now
                job.error = 'Queued request expired. Start a fresh request.'
                recovered += 1
            elif job.status == 'processing' and (job.claimed_at is None or job.claimed_at < cutoff):
                if can_retry(job.result):
                    job.status, job.worker_id, job.claimed_at = 'pending', None, None
                else:
                    job.status, job.completed_at = 'failed', now
                    job.error = 'Task interrupted repeatedly. Start a new request.'
                recovered += 1
    return recovered


async def execute(job):
    data, user_id, identifier = job['input'], job['user_id'], job['id']
    if job['operation'] == 'live_search':
        from app.jobs.router import run_manual_fetch_task
        await run_manual_fetch_task(identifier, user_id, data['title'], data['location'], data['hours_old'])
    elif job['operation'] == 'role_search':
        from app.resume.router import _run_role_fetch_task
        await _run_role_fetch_task(identifier, user_id, data['title'], data['location'], data['hours_old'])
    elif job['operation'] == 'resume_analysis':
        from app.resume.router import run_analysis_task
        await run_analysis_task(identifier, user_id, data['target_role'])
    elif job['operation'] == 'application_draft':
        from app.auth.models import DBManager
        from app.applications.router import run_apply_generation_task
        user = await run_in_threadpool(DBManager.get_user_by_id, user_id)
        if not user:
            raise ValueError('Account no longer available.')
        await run_apply_generation_task(data['job_id'], identifier, user_id, user['full_name'])
    else:
        raise ValueError('Unsupported queue operation.')


async def run_job(job_id=None):
    try:
        job = await run_in_threadpool(claim, job_id)
    except Exception as error:
        logger.warning('Queued request remains pending (%s).', type(error).__name__)
        return False
    if not job:
        return False
    token = active_worker.set(job['worker_id'])
    async def renew():
        while True:
            await asyncio.sleep(LEASE_SECONDS / 3)
            try:
                owned = await run_in_threadpool(heartbeat, job['id'], job['worker_id'])
            except Exception as error:
                logger.warning('Queue heartbeat deferred (%s).', type(error).__name__)
                return
            if not owned:
                return
    renewal = asyncio.create_task(renew())
    try:
        await execute(job)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.warning('Queued execution failed (%s).', type(error).__name__)
        await run_in_threadpool(update_job, job['id'], 'failed', error='Task execution failed. Please retry.')
    finally:
        renewal.cancel()
        with suppress(asyncio.CancelledError):
            await renewal
        # A DB failure during completion or cancellation leaves a retryable
        # request. An expired lease can also be reclaimed by another process.
        try:
            await run_in_threadpool(release, job['id'], job['worker_id'])
        except Exception as error:
            logger.warning('Queue lease release deferred (%s).', type(error).__name__)
        active_worker.reset(token)
    return True


async def consume():
    delay = 2
    next_index_repair = 0
    while True:
        try:
            if time.monotonic() >= next_index_repair:
                next_index_repair = time.monotonic() + 60
                try:
                    from app.jobs.matcher import JobMatcher
                    await run_in_threadpool(JobMatcher.reconcile_live_index, 720)
                except Exception as error:
                    logger.warning('Canonical job index repair deferred (%s).', type(error).__name__)
            await run_in_threadpool(recover_expired_leases)
            if await run_job():
                delay = 2
                continue
            delay = min(delay * 2, 30)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning('Queue storage unavailable; retrying (%s).', type(error).__name__)
            delay = min(delay * 2, 30)
        await asyncio.sleep(delay)
