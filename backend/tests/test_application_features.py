from app.auth.models import DBManager
from app.db.models import ApplicationHistory
from app.db.session import SessionLocal


def test_status_history_is_recorded_when_status_changes():
    db = SessionLocal()
    try:
        app_id = "status-test-app"
        DBManager.add_application(
            app_id=app_id,
            user_id=1,
            job_id="job-1",
            job_title="Engineer",
            company="Acme",
            applied_at="2024-01-01 00:00:00",
            status="applied",
            cover_letter="",
            resume_bullets="[]",
            notes="",
            location=None,
            job_url=None,
        )
        DBManager.update_application_status(app_id, "interview_scheduled")
        history = DBManager.get_application_status_history(app_id)
        assert any(entry["status"] == "interview_scheduled" for entry in history)
    finally:
        db.query(ApplicationHistory).filter(ApplicationHistory.id == app_id).delete(synchronize_session=False)
        db.commit()
        db.close()
