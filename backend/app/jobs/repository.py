"""Canonical Neon records for dated live listings; Chroma remains the vector index."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from app.db.models import JobPosting
from app.db.session import SessionLocal
from app.jobs.dates import posted_datetime, posted_iso


def persist_live_jobs(jobs):
    rows = [{
        'id': job['id'], 'title': job['title'], 'company': job['company'],
        'location': job.get('location'), 'description': job.get('description') or '',
        'source_url': job['url'], 'source_id': 'live:' + job['source'] + ':' + job['id'],
        'posted_at': posted_datetime(job['posted_at']), 'job_type': job.get('job_type') or 'onsite',
        'last_verified_at': datetime.now(timezone.utc), 'is_active': True,
    } for job in jobs if job.get('live_verified') is True]
    if not rows:
        return
    statement = insert(JobPosting).values(rows)
    statement = statement.on_conflict_do_update(index_elements=[JobPosting.id],
        set_={key: getattr(statement.excluded, key) for key in rows[0] if key != 'id'})
    with SessionLocal() as db:
        db.execute(statement)
        db.commit()


def list_live_jobs(hours_old=168):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    with SessionLocal() as db:
        rows = db.query(JobPosting).filter(
            JobPosting.is_active.is_(True), JobPosting.source_id.like('live:%'),
            JobPosting.posted_at >= cutoff, JobPosting.posted_at <= datetime.now(timezone.utc),
        ).order_by(JobPosting.posted_at.desc()).limit(200).all()
        return [{
            'id': row.id, 'title': row.title, 'company': row.company, 'location': row.location,
            'description': row.description, 'url': row.source_url, 'source': row.source_id.split(':')[1],
            'posted_at': posted_iso(row.posted_at), 'posted_ts': row.posted_at.timestamp(),
            'job_type': row.job_type, 'live_verified': True, 'match_score': None,
        } for row in rows]
