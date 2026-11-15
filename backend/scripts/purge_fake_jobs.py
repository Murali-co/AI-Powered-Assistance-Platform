#!/usr/bin/env python3
"""Delete obvious fake/template jobs from the local Chroma job collection.

Usage:
  python scripts/purge_fake_jobs.py --confirm
  python scripts/purge_fake_jobs.py --dry-run
"""

import argparse
from typing import Iterable, List

from app.jobs.matcher import JobMatcher


def _is_fake_job(job_meta: dict) -> bool:
    title = str(job_meta.get("title") or "").lower()
    company = str(job_meta.get("company") or "").lower()
    source = str(job_meta.get("source") or "").lower()
    if source in {"template", "mock", "fake", "scrape_fallback"}:
        return True
    if title.startswith("sample ") or title.startswith("demo "):
        return True
    if "placeholder" in title or "template" in title:
        return True
    if company in {"mock company", "sample company", "fake company"}:
        return True
    return False


def purge_fake_jobs(confirm: bool = False, dry_run: bool = False) -> List[str]:
    collection = JobMatcher.get_collection()
    results = collection.get(include=["metadatas"])
    ids = results.get("ids") or []
    metadatas = results.get("metadatas") or []
    fake_ids: List[str] = []

    for idx, job_id in enumerate(ids):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        if _is_fake_job(meta):
            fake_ids.append(str(job_id))

    if dry_run:
        print(f"Dry run: {len(fake_ids)} fake jobs would be deleted.")
        for job_id in fake_ids:
            print(job_id)
        return fake_ids

    if not confirm:
        print("Refusing to delete jobs without --confirm. Use --dry-run to preview first.")
        return []

    if fake_ids:
        collection.delete(ids=fake_ids)
        print(f"Deleted {len(fake_ids)} fake jobs from ChromaDB.")
        for job_id in fake_ids:
            print(job_id)
    else:
        print("No fake jobs found to delete.")
    return fake_ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge template/fake jobs from ChromaDB")
    parser.add_argument("--confirm", action="store_true", help="Actually delete matching jobs")
    parser.add_argument("--dry-run", action="store_true", help="Preview the fake jobs that would be removed")
    args = parser.parse_args()

    if args.dry_run and args.confirm:
        parser.error("Choose either --dry-run or --confirm, not both.")

    purge_fake_jobs(confirm=args.confirm, dry_run=args.dry_run)
