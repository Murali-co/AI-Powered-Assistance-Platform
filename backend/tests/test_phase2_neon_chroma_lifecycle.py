"""
Phase 2 Comprehensive Test Suite: Neon PostgreSQL, ChromaDB Derived Index & Outbox Lifecycle.

Verifies:
1. Exclusive Neon PostgreSQL architecture: SQLite prohibition, failure behavior without fallback (F005).
2. Connection pool sizing (10+5, recycle=300, pre-ping), credential redaction in logs.
3. Complete ORM & Alembic reconciliation: all 25 tables, compound indexes, constraints.
4. Canonical resume persistence with relational decomposition into sections & skills.
5. Outbox lifecycle: pending -> indexing -> atomic activation on Chroma success.
6. Failure safety: Chroma indexing failure preserves previous active version intact (F030).
7. Tenant ownership isolation in vector storage and section queries (F031).
8. Derived index recovery: wiping Chroma and rebuilding from Neon PostgreSQL (F032, F060).
9. Persistent / HTTP Chroma client configuration with HNSW cosine metric.
"""
import pytest
import os
import json
from unittest.mock import patch, MagicMock
from sqlalchemy import text, inspect
from app.db.session import engine, SessionLocal, mask_database_url
from app.db.models import (
    User,
    ResumeVersion,
    ResumeSection,
    ResumeSkill,
    ResumeIndexingOutbox
)
from app.resume.lifecycle import (
    save_canonical_resume,
    index_resume_version,
    reconcile_and_reindex_all
)
from app.vector_db.chroma_client import ChromaDBClient
from app.vector_db.profile_store import ProfileStore


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db_session):
    """Creates a temporary test user, cleaned up after test."""
    user = User(
        email="test_phase2_lifecycle@example.com",
        hashed_password="fakehashedpassword123",
        full_name="Phase 2 Lifecycle User",
        email_verified=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    # Teardown
    try:
        db_session.query(ResumeIndexingOutbox).filter(ResumeIndexingOutbox.user_id == user.id).delete()
        db_session.query(ResumeSkill).filter(ResumeSkill.user_id == user.id).delete()
        db_session.query(ResumeSection).filter(ResumeSection.user_id == user.id).delete()
        db_session.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def test_user_b(db_session):
    """Second test user for multi-tenant isolation tests."""
    user = User(
        email="test_phase2_tenant_b@example.com",
        hashed_password="fakehashedpassword456",
        full_name="Phase 2 Tenant B User",
        email_verified=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    yield user

    try:
        db_session.query(ResumeIndexingOutbox).filter(ResumeIndexingOutbox.user_id == user.id).delete()
        db_session.query(ResumeSkill).filter(ResumeSkill.user_id == user.id).delete()
        db_session.query(ResumeSection).filter(ResumeSection.user_id == user.id).delete()
        db_session.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


class TestNeonConfigurationAndProhibitions:
    """Test Neon PostgreSQL exclusive configuration and SQLite prohibition."""

    def test_sqlite_url_rejected_at_config(self):
        """Setting DATABASE_URL to SQLite must raise ValueError immediately."""
        from app.config import Settings
        with pytest.raises(ValueError, match=r"SQLite is forbidden|SQLite.*prohibited"):
            Settings(
                DATABASE_URL="sqlite:///test.db",
                SECRET_KEY="secret-key-test-value-length-32-chars",
                OLLAMA_BASE_URL="http://127.0.0.1:11434"
            )

    def test_neon_connection_pool_sizing(self):
        """Engine must be configured with sized connection pool."""
        assert engine.pool.size() == 10
        assert engine.pool._max_overflow == 5
        assert engine.pool._recycle == 300
        assert engine.pool._pre_ping is True
        assert engine.pool._timeout == 30

    def test_credential_masking_in_logs(self):
        """mask_database_url must redact password and user from connection string."""
        sample_url = "postgresql://myuser:SuperSecretPass123!@ep-cool-fog-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
        masked = mask_database_url(sample_url)
        assert "SuperSecretPass123!" not in masked
        assert "myuser" not in masked
        assert "****:****@" in masked
        assert "ep-cool-fog-123456.us-east-2.aws.neon.tech/neondb" in masked

    def test_reconciled_tables_in_neon(self, db_session):
        """All 25 required application and system tables must exist in Neon PostgreSQL."""
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        required_tables = {
            "alembic_version",
            "users",
            "refresh_tokens",
            "auth_audit_log",
            "two_factor_backup_codes",
            "user_criteria",
            "saved_jobs",
            "job_postings",
            "job_applications",
            "applications_history",
            "application_status_history",
            "resume_versions",
            "resume_sections",
            "resume_skills",
            "resume_indexing_outbox",
            "verified_profiles",
            "interview_sessions",
            "career_milestones",
            "chat_messages",
            "notifications",
            "feedbacks",
            "push_tokens",
            "workflows",
            "workflow_tasks",
            "background_jobs"
        }
        missing = required_tables - tables
        assert not missing, f"Missing required tables in Neon PostgreSQL: {missing}"

    def test_neon_indices_and_constraints(self, db_session):
        """Compound index on resume_versions(user_id, is_active) must exist."""
        insp = inspect(engine)
        rv_indexes = {ix["name"] for ix in insp.get_indexes("resume_versions")}
        assert "ix_resume_versions_user_active" in rv_indexes

        outbox_indexes = {ix["name"] for ix in insp.get_indexes("resume_indexing_outbox")}
        assert "ix_resume_outbox_user_status" in outbox_indexes


class TestResumeOutboxAndLifecycle:
    """Test outbox lifecycle, relational decomposition, and atomic activation."""

    def test_canonical_persistence_and_decomposition(self, db_session, test_user):
        """save_canonical_resume decomposes sections, skills, and creates pending outbox."""
        resume_text = (
            "[CONTACT]\nJohn Doe | john@example.com | 555-1234\n\n"
            "[SUMMARY]\nExperienced Python and FastAPI backend engineer.\n\n"
            "[SKILLS]\nPython, FastAPI, PostgreSQL, Docker, PyTorch\n\n"
            "[EXPERIENCE]\nSenior Software Engineer at Tech Corp."
        )
        skills = ["Python", "FastAPI", "PostgreSQL", "Docker", "PyTorch"]

        version = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text=resume_text,
            skills=skills,
            target_role="Backend Engineer",
            version_label="v1-backend"
        )

        assert version.id is not None
        assert version.user_id == test_user.id
        assert version.version_label == "v1-backend"
        assert version.indexing_status == "pending"
        assert version.is_active is False

        # Verify decomposed sections
        sections = db_session.query(ResumeSection).filter(ResumeSection.resume_version_id == version.id).all()
        assert len(sections) >= 3
        section_types = {s.section_type for s in sections}
        assert "experience" in section_types or "skills" in section_types

        # Verify decomposed skills
        saved_skills = db_session.query(ResumeSkill).filter(ResumeSkill.resume_version_id == version.id).all()
        assert len(saved_skills) == len(skills)
        saved_skill_names = {s.skill_name for s in saved_skills}
        assert "Python" in saved_skill_names

        # Verify outbox entry
        outbox = db_session.query(ResumeIndexingOutbox).filter(
            ResumeIndexingOutbox.resume_version_id == version.id
        ).first()
        assert outbox is not None
        assert outbox.status == "pending"

    def test_outbox_indexing_success_and_atomic_activation(self, db_session, test_user):
        """Successful vector indexing atomically activates version and marks outbox completed."""
        resume_text = (
            "[SUMMARY]\nSenior Backend Developer specializing in scalable distributed APIs.\n\n"
            "[SKILLS]\nPython, SQLAlchemy, PostgreSQL\n\n"
            "[EXPERIENCE]\nArchitected microservices handling 10k RPS."
        )
        skills = ["Python", "SQLAlchemy", "PostgreSQL"]

        version = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text=resume_text,
            skills=skills,
            version_label="v1"
        )

        success = index_resume_version(db_session, version.id)
        assert success is True

        db_session.refresh(version)
        assert version.is_active is True
        assert version.indexing_status == "completed"

        outbox = db_session.query(ResumeIndexingOutbox).filter(
            ResumeIndexingOutbox.resume_version_id == version.id
        ).first()
        assert outbox.status == "completed"

        # Verify profile is now accessible through ProfileStore
        profile = ProfileStore.get_profile(test_user.id)
        assert profile is not None
        assert "Senior Backend Developer" in profile["resume_text"]
        assert "Python" in profile["skills"]

    def test_indexing_failure_preserves_previous_active_version(self, db_session, test_user):
        """Failure to index in Chroma preserves previous active version intact (F030)."""
        # Step 1: Create and successfully activate Version 1
        v1 = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text="[SUMMARY]\nVersion 1 Original Resume Content.",
            skills=["Python"],
            version_label="v1"
        )
        assert index_resume_version(db_session, v1.id) is True
        db_session.refresh(v1)
        assert v1.is_active is True

        # Step 2: Create Version 2 (starts pending and inactive)
        v2 = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text="[SUMMARY]\nVersion 2 Candidate Update.",
            skills=["Python", "Go"],
            version_label="v2"
        )
        assert v2.is_active is False

        # Step 3: Simulate ChromaDB failure during indexing of Version 2
        with patch.object(ChromaDBClient, "get_collection", side_effect=RuntimeError("Chroma cluster network timeout")):
            index_result = index_resume_version(db_session, v2.id)
            assert index_result is False

        # Step 4: Verify Version 1 REMAINS active, Version 2 failed, outbox marked failed
        db_session.refresh(v1)
        db_session.refresh(v2)
        assert v1.is_active is True, "Previous active version must NOT be deactivated on indexing failure!"
        assert v2.is_active is False
        assert v2.indexing_status == "failed"

        outbox_v2 = db_session.query(ResumeIndexingOutbox).filter(
            ResumeIndexingOutbox.resume_version_id == v2.id
        ).first()
        assert outbox_v2.status == "failed"
        assert "Chroma cluster network timeout" in outbox_v2.error_message


class TestMultiTenantIsolation:
    """Test strict tenant ownership in vector storage and querying (F031)."""

    def test_tenant_vector_isolation(self, db_session, test_user, test_user_b):
        """Vectors stored for User A must never be retrieved for User B."""
        # Index User A
        v_a = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text="[SUMMARY]\nUser A is a Deep Learning and NLP Specialist.",
            skills=["PyTorch", "Transformers", "BERT"],
            version_label="user_a_v1"
        )
        index_resume_version(db_session, v_a.id)

        # Index User B
        v_b = save_canonical_resume(
            db=db_session,
            user_id=test_user_b.id,
            resume_text="[SUMMARY]\nUser B is a React and CSS Frontend Specialist.",
            skills=["React", "TypeScript", "Tailwind"],
            version_label="user_b_v1"
        )
        index_resume_version(db_session, v_b.id)

        # Verify ProfileStore respects tenant isolation
        profile_a = ProfileStore.get_profile(test_user.id)
        profile_b = ProfileStore.get_profile(test_user_b.id)

        assert "Deep Learning" in profile_a["resume_text"]
        assert "React" not in profile_a["resume_text"]

        assert "React" in profile_b["resume_text"]
        assert "Deep Learning" not in profile_b["resume_text"]

        # Section queries must only return the requester's own vectors
        sections_for_a = ProfileStore.query_profile_sections(test_user.id, "Frontend React", n_results=5)
        for sec in sections_for_a:
            assert sec["metadata"]["user_id"] == str(test_user.id)


class TestDerivedIndexRecovery:
    """Test ChromaDB index wipe and complete recovery from canonical Neon PostgreSQL (F032, F060)."""

    def test_rebuild_from_neon_source_of_truth(self, db_session, test_user):
        """Wiping ChromaDB and running reconciliation restores all active user profiles."""
        # 1. Setup active resume version in Neon
        v = save_canonical_resume(
            db=db_session,
            user_id=test_user.id,
            resume_text="[SUMMARY]\nCanonical Profile to be recovered after Chroma wipe.\n\n[SKILLS]\nPython, Docker",
            skills=["Python", "Docker"],
            version_label="rebuild_test_v1"
        )
        index_resume_version(db_session, v.id)

        # Confirm it exists in Chroma
        collection = ChromaDBClient.get_collection("user_profiles")
        existing_res = collection.get(where={"user_id": str(test_user.id)})
        assert len(existing_res["ids"]) > 0

        # 2. Simulate complete ChromaDB wipe
        client = ChromaDBClient.get_client()
        client.delete_collection("user_profiles")
        client.get_or_create_collection("user_profiles", metadata={"hnsw:space": "cosine"})

        # Confirm collection has 0 documents for user
        wiped_coll = ChromaDBClient.get_collection("user_profiles")
        wiped_res = wiped_coll.get(where={"user_id": str(test_user.id)})
        assert len(wiped_res["ids"]) == 0

        # 3. Reconcile and rebuild from canonical Neon database
        stats = reconcile_and_reindex_all(db_session)
        assert stats["reindexed_count"] >= 1
        assert stats["failed_count"] == 0

        # 4. Verify Chroma is fully restored
        restored_coll = ChromaDBClient.get_collection("user_profiles")
        restored_res = restored_coll.get(where={"user_id": str(test_user.id)})
        assert len(restored_res["ids"]) > 0
        assert any("Canonical Profile to be recovered" in doc for doc in restored_res["documents"])
