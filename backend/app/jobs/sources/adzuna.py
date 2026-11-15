import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


class AdzunaSource:
    """Adzuna job search connector."""

    @staticmethod
    def _country_code(location: Optional[str]) -> str:
        loc = (location or "").strip().lower()
        if not loc or loc in {"any", "remote", "worldwide"}:
            return "in"
        mapping = {
            "bangalore": "in", "bengaluru": "in", "mumbai": "in", "delhi": "in", "hyderabad": "in",
            "pune": "in", "chennai": "in", "kolkata": "in", "india": "in", "gurgaon": "in",
            "gurugram": "in", "noida": "in", "san francisco": "us", "new york": "us", "london": "uk",
            "toronto": "ca", "singapore": "sg", "dubai": "ae", "usa": "us", "uk": "uk", "canada": "ca",
            "australia": "au", "germany": "de", "france": "fr", "sweden": "se"
        }
        if "india" in loc:
            return "in"
        if any(country in loc for country in ["usa", "us", "america", "united states"]):
            return "us"
        return mapping.get(loc, "in")

    @staticmethod
    def _normalize_posted_at(raw_value: Any) -> str:
        if raw_value is None:
            return "Recently"
        value = str(raw_value).strip()
        if not value or value.lower() in {"nan", "recently", "just now"}:
            return "Recently"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            return value

    @classmethod
    def search(cls, search_term: str, location: str = "Any", results_wanted: int = 10, hours_old: int = 48) -> List[Dict[str, Any]]:
        app_id = (os.getenv("ADZUNA_APP_ID") or "").strip()
        api_key = (os.getenv("ADZUNA_APP_KEY") or os.getenv("ADZUNA_API_KEY") or "").strip()
        if not app_id or not api_key:
            print("  ⚠️ Adzuna credentials missing (ADZUNA_APP_ID / ADZUNA_APP_KEY). Skipping Adzuna.")
            return []

        country_code = cls._country_code(location)
        url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
        payload = {
            "app_id": app_id,
            "app_key": api_key,
            "results_per_page": max(1, min(results_wanted, 20)),
            "what": search_term,
            "sort_by": "date"
        }

        if hours_old:
            payload["max_days_old"] = max(1, int(hours_old / 24))
        if location and str(location).strip().lower() not in {"any", "", "remote", "worldwide"}:
            payload["where"] = location.strip()

        try:
            response = requests.get(url, params=payload, timeout=12)
            response.raise_for_status()
            data = response.json() or {}
            results = data.get("results") or []
        except Exception as exc:
            print(f"  ⚠️ Adzuna scrape error: {exc}")
            return []

        jobs: List[Dict[str, Any]] = []
        for item in results[:results_wanted]:
            title = (item.get("title") or "Unknown Role").strip()
            company = (item.get("company") or {}).get("display_name") or "Unknown Company"
            loc = item.get("location") or {}
            location_str = loc.get("display_name") or location or "Remote"
            description = (item.get("description") or "No description provided.").strip()
            url = item.get("redirect_url") or ""
            created = item.get("created") or "Recently"
            job_type = "remote" if "remote" in (title + description + location_str).lower() else "onsite"
            if "hybrid" in (title + description + location_str).lower():
                job_type = "hybrid"
            jobs.append({
                "id": item.get("id") or f"adzuna-{hash(title + company + location_str)}",
                "title": title,
                "company": company,
                "location": location_str,
                "description": description,
                "url": url,
                "posted_at": created,
                "posted_ts": cls._normalize_posted_at(created),
                "source": "adzuna",
                "job_type": job_type,
            })
        return jobs
