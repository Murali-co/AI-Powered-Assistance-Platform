import os
import time
import random
import hashlib
import traceback
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import requests

from app.jobs.sources.adzuna import AdzunaSource

# Import pandas and numpy for handling jobspy data
try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None
    np = None

# We will try to import jobspy but provide a robust fallback
try:
    from jobspy import scrape_jobs as jobspy_scrape
except ImportError:
    jobspy_scrape = None


# Request delay for scraper polite rate limiting (N9)
SCRAPE_REQUEST_DELAY: float = 2.0

# ─── Valid JobSpy country codes (lowercase) ───
JOBSPY_COUNTRIES = {
    "argentina", "australia", "austria", "bahrain", "belgium", "brazil",
    "canada", "chile", "china", "colombia", "costa rica", "czech republic",
    "denmark", "ecuador", "egypt", "finland", "france", "germany", "greece",
    "hong kong", "hungary", "india", "indonesia", "ireland", "israel",
    "italy", "japan", "kuwait", "luxembourg", "malaysia", "mexico",
    "morocco", "netherlands", "new zealand", "nigeria", "norway", "oman",
    "pakistan", "panama", "peru", "philippines", "poland", "portugal",
    "qatar", "romania", "saudi arabia", "singapore", "south africa",
    "south korea", "spain", "sweden", "switzerland", "taiwan", "thailand",
    "turkey", "ukraine", "united arab emirates", "uk", "usa",
    "uruguay", "venezuela", "vietnam", "worldwide",
}

# ─── Location-to-country mapping ───
LOCATION_COUNTRY_MAP = {
    # India cities
    "bangalore": "india", "bengaluru": "india", "mumbai": "india",
    "delhi": "india", "new delhi": "india", "hyderabad": "india",
    "pune": "india", "kolkata": "india", "chennai": "india",
    "gurgaon": "india", "gurugram": "india", "noida": "india",
    "coimbatore": "india", "ahmedabad": "india", "jaipur": "india",
    "lucknow": "india", "chandigarh": "india", "indore": "india",
    "kochi": "india", "visakhapatnam": "india", "bhopal": "india",
    "nagpur": "india", "surat": "india", "india": "india",
    # USA cities
    "california": "usa", "new york": "usa", "texas": "usa",
    "florida": "usa", "chicago": "usa", "boston": "usa",
    "san francisco": "usa", "seattle": "usa", "denver": "usa",
    "los angeles": "usa", "austin": "usa", "usa": "usa",
    "us": "usa", "united states": "usa", "america": "usa",
    # UK cities
    "london": "uk", "manchester": "uk", "birmingham": "uk",
    "leeds": "uk", "bristol": "uk", "edinburgh": "uk",
    "glasgow": "uk", "uk": "uk", "united kingdom": "uk",
    # Canada cities
    "toronto": "canada", "vancouver": "canada", "montreal": "canada",
    "calgary": "canada", "ottawa": "canada", "quebec": "canada",
    "canada": "canada",
    # Australia cities
    "sydney": "australia", "melbourne": "australia", "brisbane": "australia",
    "perth": "australia", "adelaide": "australia", "australia": "australia",
    # Germany cities
    "berlin": "germany", "munich": "germany", "hamburg": "germany",
    "frankfurt": "germany", "germany": "germany",
    # Singapore
    "singapore": "singapore",
    # UAE
    "dubai": "united arab emirates", "abu dhabi": "united arab emirates",
    "uae": "united arab emirates",
}


class JobScraper:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ]

    @classmethod
    def get_headers(cls) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(cls.USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

    @classmethod
    def generate_hash(cls, title: str, company: str, location: str = "") -> str:
        raw = f"{title.lower().strip()}|{company.lower().strip()}|{location.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    @classmethod
    def resolve_location(cls, location: str) -> Dict[str, Any]:
        """
        Resolve user-facing location string into JobSpy-compatible parameters.
        
        Returns a dict with:
          - country: lowercase JobSpy country string (e.g. "usa", "india")
          - search_location: city/region string to pass to JobSpy's location param, or None
          - is_remote: True if the user explicitly wants remote jobs
        """
        loc = location.strip().lower() if location else ""

        # "Any" or empty — use a safe default market instead of JobSpy's unsupported worldwide country
        if not loc or loc == "any":
            print(f"  ℹ️ Location 'Any' → defaulting to India for a stable JobSpy country and warning that worldwide is not used")
            return {"country": "india", "search_location": None, "is_remote": False}

        # "Remote" — user wants remote jobs specifically (search worldwide for remote)
        if loc == "remote":
            print(f"  ℹ️ Location 'Remote' → searching remote roles with a safe default country, without sending 'worldwide' to JobSpy")
            return {"country": "india", "search_location": None, "is_remote": True}

        # "Hybrid" / "On-site" — not geographic, search worldwide with job type filter
        if loc in ("hybrid", "on-site", "onsite"):
            print(f"  ℹ️ Location '{location}' → using default India market and filtering by job type")
            return {"country": "india", "search_location": None, "is_remote": False}

        # Try exact match in our location map
        if loc in LOCATION_COUNTRY_MAP:
            country = LOCATION_COUNTRY_MAP[loc]
            # For country-level entries (e.g. "india"), don't restrict to a city
            if loc == country or loc in ("us", "usa", "uk", "uae", "united states", "america", "united kingdom"):
                return {"country": country, "search_location": None, "is_remote": False}
            # For city-level entries, pass the city as search_location
            return {"country": country, "search_location": location.strip(), "is_remote": False}

        # Try substring matching against our map keys
        for keyword, country in LOCATION_COUNTRY_MAP.items():
            if keyword in loc:
                return {"country": country, "search_location": location.strip(), "is_remote": False}

        # Check if the raw value is itself a valid JobSpy country
        if loc in JOBSPY_COUNTRIES:
            return {"country": loc, "search_location": None, "is_remote": False}

        # Unknown location — fallback to a safe default country rather than JobSpy's unsupported worldwide value.
        print(f"⚠️ Unknown location: '{location}' — defaulting to India and keeping a location hint for filtering.")
        return {"country": "india", "search_location": location.strip(), "is_remote": False}

    @classmethod
    def run_jobspy(cls, search_term: str, location: str, results_wanted: int, hours_old: int) -> List[Dict[str, Any]]:
        """
        Scrape jobs using JobSpy library with graceful per-site fallback.
        Implements Phase-2 workflow: Scrape → Deduplicate → Filter by age → Return results
        """
        if not jobspy_scrape:
            print("❌ python-jobspy is not installed or import failed.")
            return []

        try:
            loc_info = cls.resolve_location(location)
            country = loc_info["country"]
            search_location = loc_info["search_location"]
            is_remote = loc_info["is_remote"]

            print(f"\n{'='*60}")
            print(f"🔍 SCRAPING JOBS — Phase 2 Pipeline")
            print(f"{'='*60}")
            print(f"  Search Term    : '{search_term}'")
            if country == "worldwide":
                print("  ⚠️ JobSpy country='worldwide' is not valid for Indeed; defaulting to India for a stable fallback.")
                country = "india"

            print(f"  User Location  : '{location}'")
            print(f"  Resolved Country: '{country}'")
            print(f"  Search Location : '{search_location or '(not restricted)'}'")
            print(f"  Remote Only    : {is_remote}")
            print(f"  Results Wanted : {results_wanted}")
            print(f"  Max Age (hrs)  : {hours_old}")
            print(f"{'='*60}\n")

            # Only use LinkedIn and Indeed (Glassdoor permanently disabled due to API failures)
            sites_to_try = ["linkedin", "indeed"]
            site_dfs = []
            scrape_summary = {}

            for site in sites_to_try:
                try:
                    print(f"  ⏳ Scraping {site.upper()}...")

                    scrape_params = {
                        "site_name": [site],
                        "search_term": search_term,
                        "results_wanted": max(10, results_wanted // len(sites_to_try)),
                        "hours_old": hours_old,
                        "country": country,  # Use resolved country for all sites
                    }

                    # Pass location only if we have a specific city/region
                    if search_location:
                        scrape_params["location"] = search_location

                    # Pass is_remote if user explicitly requested remote
                    if is_remote:
                        scrape_params["is_remote"] = True

                    df = jobspy_scrape(**scrape_params)

                    if df is not None and not df.empty:
                        print(f"  ✅ {site.upper()}: Fetched {len(df)} jobs")
                        site_dfs.append(df)
                        scrape_summary[site] = len(df)
                    else:
                        print(f"  ⚠️  {site.upper()}: No jobs found")
                        scrape_summary[site] = 0

                except Exception as site_err:
                    print(f"  ❌ {site.upper()}: {type(site_err).__name__}: {site_err}")
                    print(f"     Traceback:")
                    traceback.print_exc()
                    scrape_summary[site] = 0
                    # Continue with next site instead of failing
                    continue

            # Print scrape summary
            total_raw = sum(scrape_summary.values())
            print(f"\n  📊 Scrape Summary: {scrape_summary}")
            print(f"  📊 Total raw jobs fetched: {total_raw}")

            if not site_dfs or pd is None:
                print(f"  ⚠️  No data from any source")
                return []

            # Filter out empty or all-NA DataFrames, and drop completely all-NA columns to avoid deprecation warning
            non_empty_dfs = []
            for df in site_dfs:
                if df is not None and not df.empty:
                    df_cleaned = df.dropna(how='all', axis=1)
                    if not df_cleaned.empty:
                        non_empty_dfs.append(df_cleaned)

            if not non_empty_dfs:
                print(f"  ⚠️  No non-empty data from any source")
                return []

            # Concatenate results from all sources
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                jobs_df = pd.concat(non_empty_dfs, ignore_index=True)

            jobs_list = []
            if jobs_df is not None and not jobs_df.empty:
                print(f"\n  📊 Processing {len(jobs_df)} raw job listings...")

                for idx, row in jobs_df.iterrows():
                    try:
                        # Safely extract fields
                        title = str(row.get("title", "")).strip()
                        company = str(row.get("company", "")).strip()

                        # Skip malformed entries
                        if not title or not company or title == "nan" or company == "nan":
                            continue

                        location_val = str(row.get("location", "")).strip()
                        if not location_val or location_val == "nan":
                            location_val = "Not specified"
                        description = str(row.get("description", "No description provided.")).strip()
                        if description == "nan":
                            description = "No description provided."
                        url = str(row.get("job_url", "")).strip()
                        date_posted = str(row.get("date_posted", "Recently")).strip()
                        if date_posted == "nan" or not date_posted:
                            date_posted = "Recently"
                        source = str(row.get("site", "jobspy")).strip()

                        # Detect job type from description/location
                        job_type = "onsite"  # default
                        combined_text = f"{location_val} {description}".lower()
                        if "remote" in combined_text or "work from home" in combined_text or "wfh" in combined_text:
                            job_type = "remote"
                        elif "hybrid" in combined_text:
                            job_type = "hybrid"

                        jobs_list.append({
                            "title": title,
                            "company": company,
                            "location": location_val,
                            "description": description,
                            "url": url,
                            "posted_at": date_posted,
                            "posted_ts": cls._normalize_posted_at(date_posted),
                            "source": source,
                            "job_type": job_type,
                        })
                    except Exception as row_error:
                        print(f"  ⚠️  Skipping malformed job row {idx}: {row_error}")
                        continue

            print(f"  ✅ Total jobs processed from JobSpy: {len(jobs_list)}")
            
            # Generate unique IDs for all jobs before returning
            for job in jobs_list:
                if "id" not in job:
                    job["id"] = cls.generate_hash(
                        job["title"],
                        job["company"],
                        job.get("location", "")
                    )
            
            return jobs_list

        except Exception as e:
            print(f"\n  ❌ JobSpy scraping error: {e}")
            traceback.print_exc()
            return []

    @staticmethod
    def _normalize_posted_at(value: Optional[str]) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"nan", "recently", "just now"}:
            return datetime_now_str()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = __import__("datetime").datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=__import__("datetime").timezone.utc)
            return dt.astimezone(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            if any(prefix in text.lower() for prefix in ["hour", "day", "week", "month"]):
                return datetime_now_str()
            return text

    @classmethod
    def scrape_fallback(cls, search_term: str, location: str) -> List[Dict[str, Any]]:
        """Deprecated. Do not generate template jobs. If all live sources fail, return an empty list."""
        print("  ⚠️ No live results for the search. Returning an empty list instead of fake template jobs.")
        return []

    @classmethod
    def scrape_adzuna(cls, search_term: str, location: str = "Any", results_wanted: int = 20, hours_old: int = 48) -> List[Dict[str, Any]]:
        print("\nStep 1b: Trying Adzuna...")
        jobs = AdzunaSource.search(search_term, location, results_wanted, hours_old)
        if jobs:
            print(f"  ✅ Adzuna returned {len(jobs)} jobs")
        else:
            print("  ⚠️ Adzuna returned no jobs")
        return jobs

    @classmethod
    def scrape(cls, search_term: str, location: str = "Any", results_wanted: int = 20, hours_old: int = 48) -> List[Dict[str, Any]]:
        """
        Full scrape pipeline with deduplication and logging.
        """
        print(f"\n{'#'*60}")
        print(f"# AI POWERED ASSISTANCE PLATFORM SCRAPE PIPELINE START")
        print(f"# Term: '{search_term}', Location: '{location}'")
        print(f"# Results wanted: {results_wanted}, Max age: {hours_old}h")
        print(f"{'#'*60}\n")

        # Step 1: Try python-jobspy
        print("Step 1/4: Scraping job boards...")
        results = cls.run_jobspy(search_term, location, results_wanted, hours_old)
        print(f"  → Fetched {len(results)} jobs from JobSpy")

        # Step 2: Try Adzuna before Naukri, in the order JobSpy -> Adzuna -> Naukri
        if not results:
            results.extend(cls.scrape_adzuna(search_term, location, results_wanted, hours_old))

        loc_info = cls.resolve_location(location)
        if loc_info["country"] == "india" and not results:
            print("\nStep 1c: Trying Naukri.com fallback for India...")
            results.extend(cls.scrape_naukri(search_term, location, results_wanted))

        # Step 3: No fake job fallback. If the live sources return nothing, the result is empty.
        if not results:
            print("\nStep 1d: No live results from available sources. Returning empty list.")
            return []

        # Step 2/4: Deduplicate
        print(f"\nStep 2/4: Deduplicating {len(results)} jobs...")
        seen_hashes = set()
        deduplicated = []
        for job in results:
            h = cls.generate_hash(job["title"], job["company"], job.get("location", ""))
            if h not in seen_hashes:
                seen_hashes.add(h)
                job["id"] = h
                deduplicated.append(job)

        skipped = len(results) - len(deduplicated)
        print(f"  → Deduplicated to {len(deduplicated)} jobs (removed {skipped} duplicates)")

        # Step 3/4: Done — matching happens in the router after storage
        print(f"\nStep 3/4: Pipeline complete. Returning {len(deduplicated)} jobs for storage & matching.")
        print(f"{'#'*60}\n")

        # Rate limiting delay (restored 2.0s request delay as recommended in code review) (N9)
        if os.environ.get("TESTING") != "true":
            time.sleep(SCRAPE_REQUEST_DELAY)
        return deduplicated

    @classmethod
    def scrape_naukri(cls, search_term: str, location: str, results_wanted: int = 20) -> List[Dict[str, Any]]:
        """
        Scrape Naukri.com for Indian job listings.
        Note: Basic implementation using BeautifulSoup. For production, use the Naukri API.
        """
        jobs = []
        try:
            import urllib.parse
            encoded_term = urllib.parse.quote_plus(search_term or "")
            encoded_loc = urllib.parse.quote_plus(location or "")
            search_url = f"https://www.naukri.com/search?keyword={encoded_term}&location={encoded_loc}"

            response = requests.get(
                search_url,
                headers=cls.get_headers(),
                timeout=10
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            job_cards = soup.find_all('article', class_='jobTuple')[:results_wanted]

            for card in job_cards:
                try:
                    title_elem = card.find('a', class_='jobTitle')
                    company_elem = card.find('a', class_='subHead')
                    location_elem = card.find('span', class_='locWd')
                    desc_elem = card.find('span', class_='job-description')

                    if not all([title_elem, company_elem]):
                        continue

                    job_title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True)
                    job_location = location_elem.get_text(strip=True) if location_elem else location
                    job_url = title_elem.get('href', '#')
                    description = desc_elem.get_text(strip=True) if desc_elem else f"Position: {job_title}"

                    jobs.append({
                        "title": job_title,
                        "company": company,
                        "location": job_location,
                        "description": description,
                        "url": job_url if job_url.startswith('http') else f"https://naukri.com{job_url}",
                        "posted_at": "Recently",
                        "source": "naukri.com",
                        "job_type": "onsite",
                    })

                    if len(jobs) >= results_wanted:
                        break

                except Exception as e:
                    print(f"  Error parsing Naukri job card: {e}")
                    continue

            if os.environ.get("TESTING") != "true":
                time.sleep(SCRAPE_REQUEST_DELAY)

        except Exception as e:
            print(f"  Naukri scraping error: {e}")

        # Generate unique IDs for Naukri jobs
        for job in jobs:
            job["id"] = cls.generate_hash(job["title"], job["company"], job.get("location", ""))

        return jobs


def datetime_now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
