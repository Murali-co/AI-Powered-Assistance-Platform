import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.models import (
    ResumeVersion,
    ResumeSection,
    ResumeSkill,
    ResumeIndexingOutbox
)
from app.resume.cleaner import ResumeCleaner
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.embedder import embed_batch, embed_text

logger = logging.getLogger(__name__)


def save_canonical_resume(
    db: Session,
    user_id: int,
    resume_text: str,
    skills: List[str],
    target_role: Optional[str] = None,
    version_label: Optional[str] = None,
    structured_data: Optional[Dict[str, Any]] = None
) -> ResumeVersion:
    """
    Saves a canonical resume version to Neon PostgreSQL with relational decomposition
    into resume_sections and resume_skills, and enqueues an indexing outbox entry.
    Does NOT prematurely activate the new version until vector indexing succeeds.
    """
    if not version_label:
        existing_count = db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).count()
        version_label = f"v{existing_count + 1}"

    structured_json = json.dumps(structured_data) if structured_data else json.dumps({"skills": skills})

    # Check if this user currently has an active version
    has_active = db.query(ResumeVersion).filter(
        ResumeVersion.user_id == user_id,
        ResumeVersion.is_active == True
    ).first() is not None

    # New version starts as pending and inactive if an active version already exists
    # (If no active version exists, it will become active once indexed)
    new_version = ResumeVersion(
        user_id=user_id,
        resume_text=resume_text,
        version_label=version_label,
        target_role=target_role,
        structured_data=structured_json,
        is_active=False if has_active else False,
        indexing_status="pending"
    )
    db.add(new_version)
    db.flush()  # Generates new_version.id

    # Relational decomposition: sections
    sections = ResumeCleaner.segment_sections(resume_text)
    for sec_name, sec_text in sections.items():
        if sec_text.strip():
            db.add(ResumeSection(
                user_id=user_id,
                resume_version_id=new_version.id,
                section_type=sec_name,
                content=sec_text.strip()
            ))

    # Relational decomposition: skills
    for s in skills:
        if s.strip():
            db.add(ResumeSkill(
                user_id=user_id,
                resume_version_id=new_version.id,
                skill_name=s.strip()
            ))

    # Outbox indexing task
    outbox_entry = ResumeIndexingOutbox(
        user_id=user_id,
        resume_version_id=new_version.id,
        status="pending"
    )
    db.add(outbox_entry)
    db.commit()
    db.refresh(new_version)
    return new_version


def index_resume_version(db: Session, version_id: int) -> bool:
    """
    Vectorizes a canonical resume version and upserts into ChromaDB.
    Atomically activates the new version in Neon PostgreSQL ONLY upon Chroma success.
    Retains the previous active version completely intact if Chroma indexing fails.
    """
    version = db.query(ResumeVersion).filter(ResumeVersion.id == version_id).first()
    if not version:
        logger.error(f"Cannot index resume version {version_id}: not found in Neon database.")
        return False

    outbox = db.query(ResumeIndexingOutbox).filter(
        ResumeIndexingOutbox.resume_version_id == version_id
    ).first()

    if outbox:
        outbox.status = "indexing"
        outbox.attempts += 1
        db.commit()

    user_id = version.user_id
    sections = ResumeCleaner.segment_sections(version.resume_text)

    ids = []
    documents = []
    metadatas = []

    skills = []
    try:
        data = json.loads(version.structured_data or "{}")
        skills = data.get("skills", [])
    except Exception:
        skills = []
    skills_str = json.dumps(skills)

    # 1. Full document vector
    full_id = f"{user_id}_v{version_id}_full_profile"
    ids.append(full_id)
    documents.append(version.resume_text)
    metadatas.append({
        "user_id": str(user_id),
        "version_id": str(version_id),
        "type": "full",
        "skills": skills_str,
        "is_active": "true"
    })

    # 2. Section vectors
    for sec_name, sec_text in sections.items():
        if sec_text.strip():
            sec_id = f"{user_id}_v{version_id}_section_{sec_name}"
            ids.append(sec_id)
            documents.append(sec_text.strip())
            metadatas.append({
                "user_id": str(user_id),
                "version_id": str(version_id),
                "type": f"section_{sec_name}",
                "section_name": sec_name,
                "skills": skills_str,
                "is_active": "true"
            })

    try:
        embeddings = embed_batch(documents)
        collection = ChromaDBClient.get_collection("user_profiles")

        # Upsert new vectors into Chroma
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

        # Chroma write succeeded: atomically activate in Neon relational store
        # Find previous active versions to clean up their vectors later
        previous_active = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == user_id,
            ResumeVersion.id != version_id,
            ResumeVersion.is_active == True
        ).all()

        # Atomic switch in Neon
        for prev in previous_active:
            prev.is_active = False

        version.is_active = True
        version.indexing_status = "completed"
        if outbox:
            outbox.status = "completed"

        db.commit()

        # Safely remove obsolete vectors for previous active versions
        for prev in previous_active:
            try:
                collection.delete(where={
                    "$and": [
                        {"user_id": {"$eq": str(user_id)}},
                        {"version_id": {"$eq": str(prev.id)}}
                    ]
                })
            except Exception as del_err:
                logger.warning(f"Non-critical cleanup warning for old version {prev.id} vectors: {del_err}")

        # Evict in-memory profile caches
        from app.vector_db.profile_store import ProfileStore
        ProfileStore._profile_cache.pop(user_id, None)

        logger.info(f"Successfully indexed and atomically activated resume version {version_id} for user {user_id}.")
        return True

    except Exception as exc:
        db.rollback()
        error_msg = str(exc)
        logger.error(f"Failed to index resume version {version_id} in ChromaDB: {error_msg}")

        # Preserve previous active version; mark this version and outbox as failed
        if outbox:
            outbox.status = "failed"
            outbox.error_message = error_msg
        version.indexing_status = "failed"
        db.commit()
        return False


def reconcile_and_reindex_all(db: Session) -> Dict[str, Any]:
    """
    Idempotent reindexing and reconciliation script:
    Restores ChromaDB collections from canonical Neon PostgreSQL resume records.
    """
    # Fetch all users with their active or latest resume versions
    active_versions = db.query(ResumeVersion).filter(ResumeVersion.is_active == True).all()

    # If some users have resumes but none marked active, select the latest version per user
    all_user_ids = [r[0] for r in db.query(ResumeVersion.user_id).distinct().all()]
    active_user_ids = {v.user_id for v in active_versions}
    missing_user_ids = set(all_user_ids) - active_user_ids

    additional_versions = []
    for uid in missing_user_ids:
        latest = db.query(ResumeVersion).filter(
            ResumeVersion.user_id == uid
        ).order_by(ResumeVersion.created_at.desc()).first()
        if latest:
            latest.is_active = True
            db.commit()
            additional_versions.append(latest)

    target_versions = active_versions + additional_versions
    success_count = 0
    failure_count = 0
    errors = []

    for v in target_versions:
        ok = index_resume_version(db, v.id)
        if ok:
            success_count += 1
        else:
            failure_count += 1
            errors.append(f"Failed to index version {v.id} for user {v.user_id}")

    return {
        "total_candidates": len(target_versions),
        "reindexed_count": success_count,
        "failed_count": failure_count,
        "errors": errors
    }
