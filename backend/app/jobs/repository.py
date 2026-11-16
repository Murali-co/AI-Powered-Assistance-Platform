"""Canonical Neon records for dated live listings; Chroma remains the vector index."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import or_, func
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


def list_live_jobs(hours_old=168, title=None, location=None, is_remote=None, job_type=None, limit=200):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    with SessionLocal() as db:
        query = db.query(JobPosting).filter(
            JobPosting.is_active.is_(True), JobPosting.source_id.like('live:%'),
            JobPosting.posted_at >= cutoff, JobPosting.posted_at <= datetime.now(timezone.utc),
        )
        if title:
            keywords = [word.strip().lower() for word in title.split(',') if word.strip()]
            if keywords:
                query = query.filter(or_(*[or_(JobPosting.title.icontains(word, autoescape=True),
                    JobPosting.description.icontains(word, autoescape=True)) for word in keywords]))
        normalized = func.replace(func.replace(func.lower(func.coalesce(JobPosting.location, '')), 'bangalore', 'bengaluru'), 'gurgaon', 'gurugram')
        if location:
            from app.jobs.filter import normalized_location
            wanted = normalized_location(location)
            if wanted and wanted != 'any':
                predicate = normalized.icontains(wanted, autoescape=True)
                if wanted == 'remote':
                    predicate = or_(predicate, JobPosting.job_type == 'remote', normalized.icontains('anywhere', autoescape=True))
                query = query.filter(predicate)
        if is_remote:
            query = query.filter(or_(JobPosting.job_type == 'remote', normalized.icontains('remote', autoescape=True),
                normalized.icontains('anywhere', autoescape=True), JobPosting.description.icontains('work from home', autoescape=True), JobPosting.description.icontains('wfh', autoescape=True)))
        if job_type and job_type.lower() not in ('any', 'all', ''):
            actual = func.replace(func.replace(func.lower(func.coalesce(JobPosting.job_type, 'onsite')), '-', ''), '_', '')
            query = query.filter(actual == job_type.lower().replace('-', '').replace('_', ''))
        # Filter before limiting: unrelated newer roles must not hide matches.
        rows = query.order_by(JobPosting.posted_at.desc(), JobPosting.id).limit(limit).all()
        return [{
            'id': row.id, 'title': row.title, 'company': row.company, 'location': row.location,
            'description': row.description, 'url': row.source_url, 'source': row.source_id.split(':')[1],
            'posted_at': posted_iso(row.posted_at), 'posted_ts': row.posted_at.timestamp(),
            'job_type': row.job_type, 'live_verified': True, 'match_score': None,
        } for row in rows]
