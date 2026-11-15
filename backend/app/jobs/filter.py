from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class JobFilter:
    @staticmethod
    def _parse_posted_hours(job: Dict[str, Any]) -> Optional[float]:
        posted_at = job.get("posted_ts") or job.get("posted_at") or ""
        if not posted_at:
            return None

        text = str(posted_at).strip().lower()
        if not text or text == "recently":
            return 0.0

        try:
            if text.endswith("z"):
                dt = datetime.fromisoformat(text.replace("z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
        except ValueError:
            pass

        if any(prefix in text for prefix in ["hour", "hours", "day", "days", "week", "weeks", "month", "months"]):
            digits = []
            for segment in text.replace("ago", " ").split():
                try:
                    digits.append(float(segment))
                except ValueError:
                    pass
            if digits:
                hours = float(digits[0])
                if "day" in text or "days" in text:
                    hours *= 24
                elif "week" in text or "weeks" in text:
                    hours *= 24 * 7
                elif "month" in text or "months" in text:
                    hours *= 24 * 30
                return hours

        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
        except ValueError:
            return None

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
                loc_lower = location.lower().strip()
                # "Any" means no location filter
                if loc_lower and loc_lower != "any":
                    job_loc_lower = (job.get("location") or "").lower()
                    if loc_lower not in job_loc_lower:
                        # Special check: if user wants Remote, match remote/anywhere/wfh
                        if loc_lower == "remote" and ("remote" in job_loc_lower or "anywhere" in job_loc_lower):
                            pass
                        else:
                            continue

            # 3. Remote Filter (boolean)
            # Only filter out non-remote jobs if the user explicitly requested remote-only (is_remote=True)
            if is_remote:
                job_loc_lower = (job.get("location") or "").lower()
                job_desc_lower = (job.get("description") or "").lower()
                job_is_remote = (
                    "remote" in job_loc_lower
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
                if age_hours is not None and age_hours > float(hours_old):
                    continue

            filtered.append(job)
        return filtered
