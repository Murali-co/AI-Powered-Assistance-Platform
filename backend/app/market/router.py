"""Market summaries derived from recent, verified public job records."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool
from app.auth.utils import get_current_user
from app.jobs.dates import posted_datetime
from app.jobs.repository import list_live_jobs
from app.resume.extractor import SKILL_TAXONOMY

router = APIRouter(prefix="/market", tags=["market"])


def parse_relative_date(posted_str):
    parsed = posted_datetime(posted_str)
    return parsed.date().isoformat() if parsed else None


def skills_in_description(description):
    found = set()
    for keyword, skill in SKILL_TAXONOMY.items():
        # Punctuation-bearing languages (C++, C#) need explicit word boundaries.
        pattern = r"(?<!\\w)" + re.escape(keyword) + r"(?!\\w)"
        if re.search(pattern, description or '', re.IGNORECASE):
            found.add(skill)
    return found


def trending_skills(jobs):
    counts = Counter(skill for job in jobs for skill in skills_in_description(job.get('description', '')))
    return [{'skill': skill, 'count': count} for skill, count in counts.most_common(10)]


def hiring_timeline(jobs, today=None):
    today = today or datetime.now(timezone.utc).date()
    counts = Counter(date for job in jobs if (date := parse_relative_date(job.get('posted_at'))))
    return [{'date': (day := today - timedelta(days=offset)).isoformat(),
             'jobs_count': counts[day.isoformat()]} for offset in range(6, -1, -1)]


@router.get("/trending-skills")
async def get_trending_skills(current_user: dict = Depends(get_current_user)):
    return trending_skills(await run_in_threadpool(list_live_jobs, 168))


@router.get("/salary-insights")
async def get_salary_insights(current_user: dict = Depends(get_current_user)):
    # Current canonical job records have no verified salary/currency/period fields.
    # Do not substitute baseline US salaries for listings in other markets.
    return []


@router.get("/hiring-trends")
async def get_hiring_trends(current_user: dict = Depends(get_current_user)):
    return hiring_timeline(await run_in_threadpool(list_live_jobs, 168))
