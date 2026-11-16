from unittest.mock import MagicMock

import pytest


@pytest.fixture
def jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unit@ep-unit.neon.tech/unit")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from app.utils import bg_jobs
    bg_jobs.jobs_db.clear()
    return bg_jobs


def test_failed_creation_does_not_return_volatile_job(jobs, monkeypatch):
    db = MagicMock()
    db.commit.side_effect = RuntimeError("storage offline")
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    with pytest.raises(RuntimeError, match="storage is unavailable"):
        jobs.create_job(user_id=42)
    assert not jobs.jobs_db
    db.rollback.assert_called_once()
    db.close.assert_called_once()


def test_read_failure_does_not_serve_stale_memory(jobs, monkeypatch):
    db = MagicMock()
    db.query.side_effect = RuntimeError("storage offline")
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    jobs.jobs_db["old"] = {"status": "completed", "user_id": 42}
    with pytest.raises(RuntimeError, match="storage is unavailable"):
        jobs.get_job("old")


@pytest.mark.parametrize("owner", [None, 7])
def test_unowned_and_other_users_jobs_not_exposed(jobs, monkeypatch, owner):
    monkeypatch.setattr(jobs, "get_job", lambda _: {"user_id": owner})
    assert jobs.get_user_job("job", 42) is None


def test_cancelled_job_cannot_be_completed_by_late_worker(jobs, monkeypatch):
    db = MagicMock()
    record = MagicMock(status="cancelled")
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = record
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    assert jobs.update_job("job", "completed", result={"success": True}) is False
    assert record.status == "cancelled"
    db.commit.assert_not_called()


def test_failed_update_does_not_change_memory(jobs, monkeypatch):
    db = MagicMock()
    db.query.side_effect = RuntimeError("storage offline")
    monkeypatch.setattr(jobs, "SessionLocal", lambda: db)
    jobs.jobs_db["job"] = {"status": "pending"}
    assert jobs.update_job("job", "completed") is False
    assert jobs.jobs_db["job"]["status"] == "pending"


@pytest.mark.parametrize('worker', [None, 'stale-worker'])
def test_only_current_queue_lease_can_publish_results(jobs, monkeypatch, worker):
    db = MagicMock()
    record = MagicMock(status='processing', worker_id='current-worker', result={'_dispatch_version': 1})
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = record
    monkeypatch.setattr(jobs, 'SessionLocal', lambda: db)
    token = jobs.active_worker.set(worker)
    try:
        assert jobs.update_job('job', 'completed', result={'count': 1}) is False
    finally:
        jobs.active_worker.reset(token)
    db.commit.assert_not_called()
    assert record.status == 'processing'


@pytest.mark.parametrize('scheme', ['postgres://', 'postgresql://', 'postgresql+psycopg://'])
def test_failure_details_do_not_persist_connection_credentials(jobs, scheme):
    sanitized = jobs._sanitize_error('Connection failed: ' + scheme + 'synthetic:private-value@ep-unit.neon.tech/unit?token=private-token')
    assert 'private-value' not in sanitized and 'private-token' not in sanitized
