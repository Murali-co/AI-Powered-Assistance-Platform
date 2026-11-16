from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.jobs.dates import posted_datetime
import re


def normalized_location(value):
    text = str(value or '').lower().strip()
    for alias, canonical in {'bangalore': 'bengaluru', 'gurgaon': 'gurugram'}.items():
        text = re.sub(r'\b' + alias + r'\b', canonical, text)
    return text

class JobFilter:
    @staticmethod
    def live_jobs(jobs, hours_old=168):
        from urllib.parse import urlparse
        sources = {'linkedin', 'indeed', 'adzuna', 'naukri', 'naukri.com', 'remotive', 'jobicy', 'arbeitnow', 'remoteok'}
        jobs = [job for job in jobs if job.get('live_verified') is True
                and str(job.get('source', '')).lower() in sources
                and urlparse(str(job.get('url') or '')).scheme in {'http', 'https'}
                and urlparse(str(job.get('url') or '')).hostname]
        return JobFilter.filter_jobs(jobs, hours_old=hours_old)

    @staticmethod
    def _parse_posted_hours(job: Dict[str, Any]) -> Optional[float]:
        posted = posted_datetime(job.get('posted_at') or job.get('posted_ts'))
        return (datetime.now(timezone.utc) - posted).total_seconds() / 3600 if posted else None



    @staticmethod
    def filter_jobs(
        jobs: List[Dict[str, Any]],
        title: Optional[str] = None,
        location: Optional[str] = None,
        is_remote: Optional[bool] = None,
        job_type: Optional[str] = None,
        hours_old: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filtered = []
        for job in jobs:
            # 1. Title Filter
            if title:
                title_keywords = [k.strip().lower() for k in title.split(",") if k.strip()]
                job_title_lower = (job.get("title") or "").lower()
                job_desc_lower = (job.get("description") or "").lower()
                # Check if at least one keyword is in the job title or description
                if not any(kw in job_title_lower or kw in job_desc_lower for kw in title_keywords):
                    continue

            # 2. Location Filter — "Any" or empty means no restriction
            if location is not None:
                loc_lower = normalized_location(location)
                # "Any" means no location filter
                if loc_lower and loc_lower != "any":
                    job_loc_lower = normalized_location(job.get('location'))
                    if loc_lower not in job_loc_lower:
                        # Special check: if user wants Remote, match remote/anywhere/wfh
                        if loc_lower == "remote" and (job.get('job_type') == 'remote' or "remote" in job_loc_lower or "anywhere" in job_loc_lower):
                            pass
                        else:
                            continue

            # 3. Remote Filter (boolean)
            # Only filter out non-remote jobs if the user explicitly requested remote-only (is_remote=True)
            if is_remote:
                job_loc_lower = (job.get("location") or "").lower()
                job_desc_lower = (job.get("description") or "").lower()
                job_is_remote = (
                    job.get('job_type') == 'remote'
                    or "remote" in job_loc_lower
                    or "anywhere" in job_loc_lower
                    or "work from home" in job_desc_lower
                    or "wfh" in job_desc_lower
                )

                if not job_is_remote:
                    continue

            # 4. Job Type Filter (remote / hybrid / onsite)
            if job_type and job_type.lower() not in ("any", "all", ""):
                requested_type = job_type.lower().replace("-", "").replace("_", "")  # "on-site" → "onsite"
                job_actual_type = (job.get("job_type") or "onsite").lower().replace("-", "").replace("_", "")
                if requested_type != job_actual_type:
                    continue

            # 5. Maximum age filter (hours_old)
            if hours_old is not None:
                age_hours = JobFilter._parse_posted_hours(job)
                if age_hours is None or age_hours < -0.1 or age_hours > float(hours_old):
                    continue

            filtered.append(job)
        return filtered
