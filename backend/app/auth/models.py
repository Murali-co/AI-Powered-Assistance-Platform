import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, update, func, inspect, text
from app.db.session import engine, SessionLocal
from app.db.models import (
    Base,
    User,
    ApplicationHistory,
    ApplicationStatusHistory,
    UserCriteria,
    ChatMessage,
    InterviewSession,
    ResumeVersion,
    Notification,
    SavedJob,
    PushToken,
    Feedback,
    RefreshToken,
    AuthAuditLog,
    CareerMilestone,
    TwoFactorBackupCode,
    VerifiedProfile,
    JobApplication,
)
import app.orchestrator.models



def ensure_user_admin_column():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = [col["name"] for col in inspector.get_columns("users")]
    
    with engine.connect() as conn:
        # Add is_admin column if missing
        if "is_admin" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'is_admin' column to users table")
        
        # Add email_notifications column if missing
        if "email_notifications" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT 1"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT TRUE"))
            print("✅ Added 'email_notifications' column to users table")
        
        # Add two_factor_enabled column if missing
        if "two_factor_enabled" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'two_factor_enabled' column to users table")

        # Add two_factor_secret column if missing
        if "two_factor_secret" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_secret VARCHAR"))
            print("✅ Added 'two_factor_secret' column to users table")

        # Add last_totp_step column if missing
        if "last_totp_step" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_totp_step INTEGER NULL"))
            print("✅ Added 'last_totp_step' column to users table")

        # Add daily_digest column if missing
        if "daily_digest" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN daily_digest BOOLEAN DEFAULT 1"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN daily_digest BOOLEAN DEFAULT TRUE"))
            print("✅ Added 'daily_digest' column to users table")
        
        # Add scrape_frequency_hours column if missing
        if "scrape_frequency_hours" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN scrape_frequency_hours INTEGER DEFAULT 12"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN scrape_frequency_hours INTEGER DEFAULT 12"))
            print("✅ Added 'scrape_frequency_hours' column to users table")

        # Add email verification columns if missing
        if "email_verified" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'email_verified' column to users table")

        if "verification_token" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR NULL"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_verification_token ON users (verification_token)"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR NULL UNIQUE"))
            print("✅ Added 'verification_token' column to users table")

        if "verification_token_expiry" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_token_expiry TIMESTAMP NULL"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_token_expiry TIMESTAMP WITH TIME ZONE NULL"))
            print("✅ Added 'verification_token_expiry' column to users table")

        if "reset_password_token" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token VARCHAR NULL"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_reset_password_token ON users (reset_password_token)"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token VARCHAR NULL UNIQUE"))
            print("✅ Added 'reset_password_token' column to users table")

        if "reset_password_token_expiry" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token_expiry TIMESTAMP NULL"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN reset_password_token_expiry TIMESTAMP WITH TIME ZONE NULL"))
            print("✅ Added 'reset_password_token_expiry' column to users table")

        if "auto_approve_external_actions" not in columns:
            if engine.dialect.name == "sqlite":
                conn.execute(text("ALTER TABLE users ADD COLUMN auto_approve_external_actions BOOLEAN NOT NULL DEFAULT 0"))
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN auto_approve_external_actions BOOLEAN NOT NULL DEFAULT FALSE"))
            print("✅ Added 'auto_approve_external_actions' column to users table")
        
        # Ensure user criteria table has job_type support
        if "user_criteria" in inspector.get_table_names():
            user_criteria_cols = [col["name"] for col in inspector.get_columns("user_criteria")]
            if "job_type" not in user_criteria_cols:
                conn.execute(text("ALTER TABLE user_criteria ADD COLUMN job_type VARCHAR NULL"))
                print("✅ Added 'job_type' column to user_criteria table")
        
        # Ensure applications_history table has location and job_url columns
        if "applications_history" in inspector.get_table_names():
            app_history_cols = [col["name"] for col in inspector.get_columns("applications_history")]
            if "location" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN location VARCHAR NULL"))
                print("✅ Added 'location' column to applications_history table")
            if "job_url" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN job_url VARCHAR NULL"))
                print("✅ Added 'job_url' column to applications_history table")
            if "resume_version_id" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN resume_version_id INTEGER NULL"))
                print("✅ Added 'resume_version_id' column to applications_history table")
            if "tone" not in app_history_cols:
                conn.execute(text("ALTER TABLE applications_history ADD COLUMN tone VARCHAR NULL"))
                print("✅ Added 'tone' column to applications_history table")

        if "saved_jobs" in inspector.get_table_names():
            saved_job_cols = [col["name"] for col in inspector.get_columns("saved_jobs")]
            if "stage" not in saved_job_cols:
                conn.execute(text("ALTER TABLE saved_jobs ADD COLUMN stage VARCHAR NULL DEFAULT 'saved'"))
                print("✅ Added 'stage' column to saved_jobs table")

        # Ensure refresh_tokens table has replaced_by and auth_time columns
        if "refresh_tokens" in inspector.get_table_names():
            rt_cols = [col["name"] for col in inspector.get_columns("refresh_tokens")]
            if "replaced_by" not in rt_cols:
                conn.execute(text("ALTER TABLE refresh_tokens ADD COLUMN replaced_by VARCHAR(64) NULL"))
                print("✅ Added 'replaced_by' column to refresh_tokens table")
            if "auth_time" not in rt_cols:
                conn.execute(text("ALTER TABLE refresh_tokens ADD COLUMN auth_time INTEGER NULL"))
                print("✅ Added 'auth_time' column to refresh_tokens table")

        # Ensure auth_audit_log table has email column
        if "auth_audit_log" in inspector.get_table_names():
            audit_cols = [col["name"] for col in inspector.get_columns("auth_audit_log")]
            if "email" not in audit_cols:
                conn.execute(text("ALTER TABLE auth_audit_log ADD COLUMN email VARCHAR(255) NULL"))
                print("✅ Added 'email' column to auth_audit_log table")

        conn.commit()


# Notice: Schema evolution should be managed via Alembic migrations.
# Base.metadata.create_all is deferred to explicit test/initialization scripts via init_db().

def init_db():
    """Compatibility helper used by tests or explicit setup scripts to create tables."""
    Base.metadata.create_all(bind=engine)
    ensure_user_admin_column()


def model_to_dict(inst) -> Dict[str, Any]:
    res = {}
    for c in inst.__table__.columns:
        val = getattr(inst, c.name)
        # Convert datetimes to ISO strings for compatibility with existing API
        if isinstance(val, datetime):
            res[c.name] = val.isoformat(sep=' ')
            continue
        res[c.name] = val
    return res


class DBManager:
    @staticmethod
    def create_user(email: str, hashed_pw: str, full_name: str) -> Optional[int]:
        db = SessionLocal()
        clean_email = email.strip().lower()
        clean_name = full_name.strip()
        try:
            user = User(
                email=clean_email,
                hashed_password=hashed_pw,
                full_name=clean_name,
                is_admin=False
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def promote_user_to_admin(email: str) -> bool:
        db = SessionLocal()
        try:
            stmt = update(User).where(User.email == email).values(is_admin=True)
            res = db.execute(stmt)
            db.commit()
            return res.rowcount > 0
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def delete_user(user_id: int) -> None:
        db = SessionLocal()
        try:
            # 1. Purge all child records referencing user_id to prevent FK constraint violations
            app_ids = [row[0] for row in db.query(ApplicationHistory.id).filter(ApplicationHistory.user_id == user_id).all()]
            if app_ids:
                db.query(ApplicationStatusHistory).filter(ApplicationStatusHistory.application_id.in_(app_ids)).delete(synchronize_session=False)

            db.query(ApplicationHistory).filter(ApplicationHistory.user_id == user_id).delete(synchronize_session=False)
            db.query(UserCriteria).filter(UserCriteria.user_id == user_id).delete(synchronize_session=False)
            db.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete(synchronize_session=False)
            db.query(InterviewSession).filter(InterviewSession.user_id == user_id).delete(synchronize_session=False)
            db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).delete(synchronize_session=False)
            db.query(CareerMilestone).filter(CareerMilestone.user_id == user_id).delete(synchronize_session=False)
            db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
            db.query(SavedJob).filter(SavedJob.user_id == user_id).delete(synchronize_session=False)
            db.query(PushToken).filter(PushToken.user_id == user_id).delete(synchronize_session=False)
            db.query(JobApplication).filter(JobApplication.user_id == user_id).delete(synchronize_session=False)
            db.query(Feedback).filter(Feedback.user_id == user_id).delete(synchronize_session=False)
            db.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(synchronize_session=False)
            db.query(AuthAuditLog).filter(AuthAuditLog.user_id == user_id).delete(synchronize_session=False)
            db.query(VerifiedProfile).filter(VerifiedProfile.user_id == user_id).delete(synchronize_session=False)
            try:
                from app.db.models import BackgroundJob
                db.query(BackgroundJob).filter(BackgroundJob.user_id == user_id).delete(synchronize_session=False)
            except Exception:
                pass

            # Purge workflows if any
            try:
                from app.orchestrator.models import WorkflowModel, WorkflowTaskModel
                wf_ids = [row[0] for row in db.query(WorkflowModel.id).filter(WorkflowModel.user_id == user_id).all()]
                if wf_ids:
                    db.query(WorkflowTaskModel).filter(WorkflowTaskModel.workflow_id.in_(wf_ids)).delete(synchronize_session=False)
                db.query(WorkflowModel).filter(WorkflowModel.user_id == user_id).delete(synchronize_session=False)
            except Exception:
                pass

            # 2. Delete user record
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()

            # 3. Purge profile and application vector embeddings from ChromaDB
            try:
                from app.vector_db.profile_store import ProfileStore
                ProfileStore.delete_profile(user_id)
            except Exception:
                pass

            try:
                from app.vector_db.chroma_client import ChromaDBClient
                app_col = ChromaDBClient.get_collection("applications")
                app_col.delete(where={"user_id": str(user_id)})
            except Exception:
                pass

            # 4. Clean user uploaded files
            try:
                from pathlib import Path
                from app.config import settings
                upload_dir = Path(settings.UPLOAD_DIR)
                if upload_dir.exists():
                    for f in upload_dir.glob(f"{user_id}_*"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                    user_subdir = upload_dir / str(user_id)
                    if user_subdir.exists() and user_subdir.is_dir():
                        import shutil
                        shutil.rmtree(user_subdir, ignore_errors=True)
            except Exception:
                pass
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        if not email:
            return None
        clean_email = email.strip().lower()
        db = SessionLocal()
        try:
            user = db.query(User).filter(func.lower(User.email) == clean_email).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def update_auto_approve_external_actions(user_id: int, auto_approve: bool) -> None:
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if user:
                user.auto_approve_external_actions = auto_approve
                db.commit()
        finally:
            db.close()

    @staticmethod
    def get_criteria(user_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            crit = db.get(UserCriteria, user_id)
            if crit:
                res = model_to_dict(crit)
                return res
            return None
        finally:
            db.close()

    @staticmethod
    def save_criteria(user_id: int, title: Optional[str], location: Optional[str], is_remote: Optional[bool], job_type: Optional[str] = None, hours_old: int = 48):
        db = SessionLocal()
        try:
            obj = UserCriteria(
                user_id=user_id,
                title=title,
                location=location,
                is_remote=is_remote,
                job_type=job_type,
                hours_old=hours_old,
            )
            db.merge(obj)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def add_application(app_id: str, user_id: int, job_id: str, job_title: str, company: str, applied_at, status: str, cover_letter: str, resume_bullets: str, notes: str, location: Optional[str] = None, job_url: Optional[str] = None, resume_version_id: Optional[int] = None, tone: Optional[str] = None):
        db = SessionLocal()
        try:
            # Accept string timestamps for backward compatibility
            if isinstance(applied_at, str):
                try:
                    applied_at_dt = datetime.fromisoformat(applied_at)
                except Exception:
                    # fallback: try common format
                    applied_at_dt = datetime.strptime(applied_at, "%Y-%m-%d %H:%M:%S")
            else:
                applied_at_dt = applied_at

            app = ApplicationHistory(
                id=app_id,
                user_id=user_id,
                job_id=job_id,
                job_title=job_title,
                company=company,
                applied_at=applied_at_dt,
                status=status,
                cover_letter=cover_letter,
                resume_bullets=resume_bullets,
                notes=notes,
                location=location,
                job_url=job_url,
                resume_version_id=resume_version_id,
                tone=tone,
            )
            db.add(app)
            db.commit()
            db.refresh(app)
            DBManager.record_status_history(app.id, status)
        finally:
            db.close()

    @staticmethod
    def get_applications(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(ApplicationHistory).filter(ApplicationHistory.user_id == user_id).order_by(ApplicationHistory.applied_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_application(app_id: str, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a single application by ID, ensuring user owns it"""
        db = SessionLocal()
        try:
            row = db.query(ApplicationHistory).filter(
                ApplicationHistory.id == app_id,
                ApplicationHistory.user_id == user_id
            ).first()
            return model_to_dict(row) if row else None
        finally:
            db.close()

    @staticmethod
    def create_interview_session(
        session_id: str,
        user_id: int,
        job_id: Optional[str],
        target_role: Optional[str],
        chat_history: str,
        interview_mode: Optional[str] = None,
        difficulty_level: int = 3,
        topics_covered: str = "[]",
        metadata_json: Optional[str] = None
    ):
        db = SessionLocal()
        try:
            session = InterviewSession(
                id=session_id,
                user_id=user_id,
                job_id=job_id,
                target_role=target_role,
                interview_mode=interview_mode,
                chat_history=chat_history,
                difficulty_level=difficulty_level,
                topics_covered=topics_covered,
                metadata_json=metadata_json
            )
            db.add(session)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_interview_session(session_id: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            s = db.get(InterviewSession, session_id)
            return model_to_dict(s) if s else None
        finally:
            db.close()

    @staticmethod
    def update_interview_session(
        session_id: str,
        chat_history: str,
        is_finished: bool,
        feedback: Optional[str] = None,
        score: Optional[int] = None,
        difficulty_level: Optional[int] = None,
        topics_covered: Optional[str] = None,
        metadata_json: Optional[str] = None
    ):
        db = SessionLocal()
        try:
            values = {
                "chat_history": chat_history,
                "is_finished": is_finished,
                "feedback": feedback,
                "score": score,
            }
            if difficulty_level is not None:
                values["difficulty_level"] = difficulty_level
            if topics_covered is not None:
                values["topics_covered"] = topics_covered
            if metadata_json is not None:
                values["metadata_json"] = metadata_json

            stmt = update(InterviewSession).where(InterviewSession.id == session_id).values(**values)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_interviews(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(InterviewSession).filter(InterviewSession.user_id == user_id).order_by(InterviewSession.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def save_resume_version(user_id: int, resume_text: str, label: str, target_role: Optional[str] = None):
        db = SessionLocal()
        try:
            rv = ResumeVersion(user_id=user_id, resume_text=resume_text, version_label=label, target_role=target_role)
            db.add(rv)
            db.commit()
            return rv.id
        finally:
            db.close()

    @staticmethod
    def get_resume_versions(user_id: int) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).order_by(ResumeVersion.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_resume_version_by_id(version_id: int) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            r = db.get(ResumeVersion, version_id)
            return model_to_dict(r) if r else None
        finally:
            db.close()

    @staticmethod
    def delete_resume_version(version_id: int, user_id: int) -> bool:
        db = SessionLocal()
        try:
            rv = db.query(ResumeVersion).filter(ResumeVersion.id == version_id, ResumeVersion.user_id == user_id).first()
            if rv:
                db.delete(rv)
                db.commit()
                return True
            return False
        finally:
            db.close()

    @staticmethod
    def add_notification(user_id: int, title: str, message: str, type: str):
        db = SessionLocal()
        try:
            n = Notification(user_id=user_id, title=title, message=message, type=type)
            db.add(n)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_notifications(user_id: int, only_unread: bool = False) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            q = db.query(Notification).filter(Notification.user_id == user_id)
            if only_unread:
                q = q.filter(Notification.is_read == False)
            rows = q.order_by(Notification.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def mark_notification_read(notification_id: int, user_id: int):
        db = SessionLocal()
        try:
            stmt = update(Notification).where(Notification.id == notification_id, Notification.user_id == user_id).values(is_read=True)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def mark_all_notifications_read(user_id: int):
        db = SessionLocal()
        try:
            stmt = update(Notification).where(Notification.user_id == user_id).values(is_read=True)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_admin_metrics() -> Dict[str, Any]:
        db = SessionLocal()
        try:
            total_users = db.query(func.count(User.id)).scalar() or 0
            total_chats = db.query(func.count(ChatMessage.id)).scalar() or 0
            total_apps = db.query(func.count(ApplicationHistory.id)).scalar() or 0
            total_interviews = db.query(func.count(InterviewSession.id)).scalar() or 0
            return {
                "total_users": total_users,
                "total_chats": total_chats,
                "total_applications": total_apps,
                "total_interviews": total_interviews,
            }
        finally:
            db.close()

    @staticmethod
    def update_password(user_id: int, hashed_pw: str):
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(hashed_password=hashed_pw)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_application_status(app_id: str, status: str):
        """Update application status and record history"""
        db = SessionLocal()
        try:
            stmt = update(ApplicationHistory).where(ApplicationHistory.id == app_id).values(status=status)
            db.execute(stmt)
            db.commit()
            DBManager.record_status_history(app_id, status)
        finally:
            db.close()

    @staticmethod
    def record_status_history(app_id: str, status: str):
        db = SessionLocal()
        try:
            history_entry = ApplicationStatusHistory(application_id=app_id, status=status)
            db.add(history_entry)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_application_status_history(app_id: str) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = db.query(ApplicationStatusHistory).filter(ApplicationStatusHistory.application_id == app_id).order_by(ApplicationStatusHistory.changed_at.asc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def save_job(user_id: int, job_id: str, job_title: str, company: str, location: Optional[str] = None, job_url: Optional[str] = None, notes: Optional[str] = None, stage: Optional[str] = None) -> Optional[int]:
        """Save a job for later reference"""
        db = SessionLocal()
        try:
            # Check if already saved
            existing = db.query(SavedJob).filter(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id
            ).first()
            if existing:
                return existing.id
            
            saved_job = SavedJob(
                user_id=user_id,
                job_id=job_id,
                job_title=job_title,
                company=company,
                location=location,
                job_url=job_url,
                notes=notes,
                stage=stage or "saved"
            )
            db.add(saved_job)
            db.commit()
            db.refresh(saved_job)
            return saved_job.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_saved_jobs(user_id: int) -> List[Dict[str, Any]]:
        """Get all saved jobs for a user"""
        db = SessionLocal()
        try:
            rows = db.query(SavedJob).filter(SavedJob.user_id == user_id).order_by(SavedJob.saved_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def update_saved_job_stage(saved_job_id: int, user_id: int, stage: str):
        db = SessionLocal()
        try:
            stmt = update(SavedJob).where(SavedJob.id == saved_job_id, SavedJob.user_id == user_id).values(stage=stage)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def save_push_token(user_id: int, token: str, device_type: Optional[str] = None):
        db = SessionLocal()
        try:
            existing = db.query(PushToken).filter(PushToken.user_id == user_id, PushToken.token == token).first()
            if existing:
                existing.device_type = device_type or existing.device_type or "web"
                db.commit()
                return existing.id
            push_token = PushToken(user_id=user_id, token=token, device_type=device_type or "web")
            db.add(push_token)
            db.commit()
            db.refresh(push_token)
            return push_token.id
        finally:
            db.close()

    @staticmethod
    def unsave_job(user_id: int, job_id: str) -> bool:
        """Remove a saved job"""
        db = SessionLocal()
        try:
            stmt = text("DELETE FROM saved_jobs WHERE user_id = :user_id AND job_id = :job_id")
            result = db.execute(stmt, {"user_id": user_id, "job_id": job_id})
            db.commit()
            return result.rowcount > 0
        finally:
            db.close()

    @staticmethod
    def is_job_saved(user_id: int, job_id: str) -> bool:
        """Check if a job is saved by user"""
        db = SessionLocal()
        try:
            exists = db.query(SavedJob).filter(
                SavedJob.user_id == user_id,
                SavedJob.job_id == job_id
            ).first() is not None
            return exists
        finally:
            db.close()

    @staticmethod
    def update_user_full_name(user_id: int, full_name: str):
        """Update user's full name"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(full_name=full_name)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_user_preference(user_id: int, preference: str, value: Any):
        """Update a specific user preference"""
        db = SessionLocal()
        try:
            valid_preferences = {"email_notifications", "daily_digest", "scrape_frequency_hours", "preferred_model"}
            if preference not in valid_preferences:
                raise ValueError(f"Invalid preference: {preference}")
            
            stmt = update(User).where(User.id == user_id).values({getattr(User, preference): value})
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== EMAIL VERIFICATION METHODS =====
    @staticmethod
    def set_verification_token(user_id: int, token: str, expiry: datetime):
        """Store verification token hash for a user (N2)"""
        from app.auth.utils import hash_token
        clean_tok = token.strip()
        is_hash = len(clean_tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in clean_tok)
        token_hash = clean_tok if is_hash else hash_token(clean_tok)
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                verification_token=token_hash,
                verification_token_expiry=expiry
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_by_verification_token(token: str) -> Optional[Dict[str, Any]]:
        """Get user by verification token"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.verification_token == token).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def verify_email(user_id: int):
        """Mark email as verified"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                email_verified=True,
                verification_token=None,
                verification_token_expiry=None
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== PASSWORD RESET METHODS =====
    @staticmethod
    def set_reset_password_token(user_id: int, token: str, expiry: datetime):
        """Store password reset token hash for a user (N2)"""
        from app.auth.utils import hash_token
        clean_tok = token.strip()
        is_hash = len(clean_tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in clean_tok)
        token_hash = clean_tok if is_hash else hash_token(clean_tok)
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                reset_password_token=token_hash,
                reset_password_token_expiry=expiry
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
        """Get user by password reset token"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.reset_password_token == token).first()
            return model_to_dict(user) if user else None
        finally:
            db.close()

    @staticmethod
    def reset_password(user_id: int, hashed_password: str):
        """Reset password and clear token"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(
                hashed_password=hashed_password,
                reset_password_token=None,
                reset_password_token_expiry=None
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    # ===== JOB APPLICATION METHODS =====
    @staticmethod
    def create_job_application(user_id: int, job_id: str, company: str, title: str, 
                              location: Optional[str] = None, job_url: Optional[str] = None,
                              cover_letter: Optional[str] = None, notes: Optional[str] = None) -> Optional[int]:
        """Create a new job application"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            # Check if already applied
            existing = db.query(JobApplication).filter(
                JobApplication.user_id == user_id,
                JobApplication.job_id == job_id
            ).first()
            if existing:
                return existing.id
            
            app = JobApplication(
                user_id=user_id,
                job_id=job_id,
                company=company,
                title=title,
                location=location,
                job_url=job_url,
                cover_letter=cover_letter,
                notes=notes,
                status="pending"
            )
            db.add(app)
            db.commit()
            db.refresh(app)
            return app.id
        except IntegrityError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_job_applications(user_id: int, status: Optional[str] = None, skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get job applications for a user"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            q = db.query(JobApplication).filter(JobApplication.user_id == user_id)
            if status:
                q = q.filter(JobApplication.status == status)
            rows = q.order_by(JobApplication.applied_date.desc()).offset(skip).limit(limit).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_job_application(app_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific job application"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            app = db.query(JobApplication).filter(
                JobApplication.id == app_id,
                JobApplication.user_id == user_id
            ).first()
            return model_to_dict(app) if app else None
        finally:
            db.close()

    @staticmethod
    def update_job_application_status(app_id: int, status: str):
        """Update job application status"""
        from app.db.models import JobApplication
        db = SessionLocal()
        try:
            stmt = update(JobApplication).where(JobApplication.id == app_id).values(status=status)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_weekly_applications(user_id: int, days: int = 7) -> List[Dict[str, Any]]:
        """Get applications from the last N days"""
        from app.db.models import JobApplication
        from datetime import datetime, timedelta
        db = SessionLocal()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            rows = db.query(JobApplication).filter(
                JobApplication.user_id == user_id,
                JobApplication.applied_date >= cutoff_date
            ).order_by(JobApplication.applied_date.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def get_all_users() -> List[Dict[str, Any]]:
        """Get all users (for scheduled jobs and notifications)"""
        db = SessionLocal()
        try:
            users = db.query(User).all()
            return [model_to_dict(u) for u in users]
        finally:
            db.close()

    @staticmethod
    def create_feedback(user_id: int, feedback_text: str) -> Optional[int]:
        """Save user feedback to database"""
        db = SessionLocal()
        try:
            fb = Feedback(user_id=user_id, feedback_text=feedback_text)
            db.add(fb)
            db.commit()
            db.refresh(fb)
            return fb.id
        except Exception as e:
            db.rollback()
            print(f"[DB] Failed to save feedback to database: {e}")
            return None
        finally:
            db.close()

    # ===== WORKFLOW ORCHESTRATOR METHODS =====
    @staticmethod
    def save_workflow(wf_dict: Dict[str, Any]):
        from app.orchestrator.models import WorkflowModel
        db = SessionLocal()
        try:
            wf = WorkflowModel(
                id=wf_dict["workflow_id"],
                user_id=wf_dict["user_id"],
                goal=wf_dict["goal"],
                status=wf_dict.get("status", "PENDING"),
                error=wf_dict.get("error")
            )
            db.add(wf)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_workflow_status(workflow_id: str, status: str):
        from app.orchestrator.models import WorkflowModel
        db = SessionLocal()
        try:
            stmt = update(WorkflowModel).where(WorkflowModel.id == workflow_id).values(status=status)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def finish_workflow(workflow_id: str, status: str, error: Optional[str] = None, completed_at: Optional[str] = None):
        from app.orchestrator.models import WorkflowModel
        db = SessionLocal()
        try:
            completed_dt = None
            if completed_at:
                try:
                    completed_dt = datetime.fromisoformat(completed_at)
                except Exception:
                    completed_dt = datetime.now()
            stmt = update(WorkflowModel).where(WorkflowModel.id == workflow_id).values(
                status=status,
                error=error,
                completed_at=completed_dt or datetime.now()
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_workflow_tasks(workflow_id: str, tasks_list: List[Dict[str, Any]]):
        from app.orchestrator.models import WorkflowTaskModel
        import json
        db = SessionLocal()
        try:
            for t in tasks_list:
                db_id = f"{workflow_id}:{t['task_id']}"
                existing = db.get(WorkflowTaskModel, db_id)
                if existing:
                    existing.status = t.get("status", "PENDING")
                    existing.input_json = json.dumps(t.get("input", {}))
                    existing.output_json = json.dumps(t.get("output")) if t.get("output") is not None else None
                    existing.dependencies_json = json.dumps(t.get("dependencies", []))
                    existing.error = t.get("error")
                else:
                    task_obj = WorkflowTaskModel(
                        id=db_id,
                        task_id=t["task_id"],
                        workflow_id=workflow_id,
                        task_type=t["task_type"],
                        description=t["description"],
                        status=t.get("status", "PENDING"),
                        input_json=json.dumps(t.get("input", {})),
                        output_json=json.dumps(t.get("output")) if t.get("output") is not None else None,
                        dependencies_json=json.dumps(t.get("dependencies", [])),
                        error=t.get("error")
                    )
                    db.add(task_obj)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_task_status(workflow_id: str, task_id: str, status: str):
        from app.orchestrator.models import WorkflowTaskModel
        db = SessionLocal()
        try:
            db_id = f"{workflow_id}:{task_id}"
            stmt = update(WorkflowTaskModel).where(WorkflowTaskModel.id == db_id).values(status=status)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_task_output(workflow_id: str, task_id: str, status: str, output: Dict[str, Any], completed_at: str):
        from app.orchestrator.models import WorkflowTaskModel
        import json
        db = SessionLocal()
        try:
            db_id = f"{workflow_id}:{task_id}"
            stmt = update(WorkflowTaskModel).where(WorkflowTaskModel.id == db_id).values(
                status=status,
                output_json=json.dumps(output)
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def update_task_error(workflow_id: str, task_id: str, status: str, error: str, completed_at: str):
        from app.orchestrator.models import WorkflowTaskModel
        db = SessionLocal()
        try:
            db_id = f"{workflow_id}:{task_id}"
            stmt = update(WorkflowTaskModel).where(WorkflowTaskModel.id == db_id).values(
                status=status,
                error=error
            )
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
        from app.orchestrator.models import WorkflowModel, WorkflowTaskModel
        import json
        db = SessionLocal()
        try:
            wf = db.get(WorkflowModel, workflow_id)
            if not wf:
                return None
            res = model_to_dict(wf)
            res["workflow_id"] = wf.id
            
            tasks_rows = db.query(WorkflowTaskModel).filter(WorkflowTaskModel.workflow_id == workflow_id).order_by(WorkflowTaskModel.created_at.asc()).all()
            tasks = []
            for tr in tasks_rows:
                td = model_to_dict(tr)
                td["task_id"] = tr.task_id
                td["input"] = json.loads(tr.input_json) if tr.input_json else {}
                td["output"] = json.loads(tr.output_json) if tr.output_json else None
                td["dependencies"] = json.loads(tr.dependencies_json) if tr.dependencies_json else []
                tasks.append(td)
            res["tasks"] = tasks
            return res
        finally:
            db.close()

    @staticmethod
    def get_user_workflows(user_id: int) -> List[Dict[str, Any]]:
        from app.orchestrator.models import WorkflowModel
        db = SessionLocal()
        wf_ids = []
        try:
            rows = db.query(WorkflowModel.id).filter(WorkflowModel.user_id == user_id).order_by(WorkflowModel.created_at.desc()).all()
            wf_ids = [r.id for r in rows]
        finally:
            db.close()

        results = []
        for wf_id in wf_ids:
            wf_dict = DBManager.get_workflow(wf_id)
            if wf_dict:
                results.append(wf_dict)
        return results

    # ===== REFRESH TOKEN METHODS =====
    @staticmethod
    def create_refresh_token(
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        replaced_by: Optional[str] = None,
        auth_time: Optional[int] = None
    ) -> int:
        """Create and persist a new refresh token. Raises on error to prevent setting cookies on unpersisted sessions."""
        db = SessionLocal()
        try:
            rt = RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
                replaced_by=replaced_by,
                auth_time=auth_time
            )
            db.add(rt)
            db.commit()
            db.refresh(rt)
            return rt.id
        except Exception as e:
            db.rollback()
            print(f"[DB] Failed to create refresh token: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def rotate_refresh_token_atomic(
        old_token_hash: str,
        new_token_hash: str,
        user_id: int,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        auth_time: Optional[int] = None
    ) -> Optional[int]:
        """
        Atomically revoke old token and insert new token in a single conditional operation.
        Only one concurrent request can consume the old token (WHERE revoked_at IS NULL).
        Returns new token ID on success, None if old token was already consumed/revoked.
        """
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            # Conditional update: only succeeds if revoked_at IS NULL and expires_at > now
            stmt = (
                update(RefreshToken)
                .where(
                    RefreshToken.token_hash == old_token_hash,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now
                )
                .values(
                    revoked_at=now,
                    replaced_by=new_token_hash
                )
            )
            res = db.execute(stmt)
            if res.rowcount == 0:
                # Lost the race: another concurrent request consumed this token or token expired
                db.rollback()
                return None

            new_rt = RefreshToken(
                user_id=user_id,
                token_hash=new_token_hash,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
                auth_time=auth_time
            )
            db.add(new_rt)
            db.commit()
            db.refresh(new_rt)
            return new_rt.id
        except Exception as e:
            db.rollback()
            print(f"[DB] Failed during atomic token rotation: {e}")
            raise
        finally:
            db.close()

    @staticmethod
    def get_refresh_token_by_hash(token_hash: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
            return model_to_dict(rt) if rt else None
        finally:
            db.close()

    @staticmethod
    def revoke_refresh_token(token_hash: str):
        db = SessionLocal()
        try:
            stmt = update(RefreshToken).where(RefreshToken.token_hash == token_hash).values(revoked_at=datetime.now(timezone.utc))
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def revoke_all_user_refresh_tokens(user_id: int):
        """Revoke all refresh tokens for a user (used when replay attack detected or password changed/reset)"""
        db = SessionLocal()
        try:
            stmt = update(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)
            ).values(revoked_at=datetime.now(timezone.utc))
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_active_user_sessions(user_id: int) -> List[Dict[str, Any]]:
        """Get active non-revoked non-expired sessions for a user"""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            rows = db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now
            ).order_by(RefreshToken.created_at.desc()).all()
            return [model_to_dict(r) for r in rows]
        finally:
            db.close()

    @staticmethod
    def revoke_session_by_id(session_id: int, user_id: int) -> bool:
        """Revoke a specific session by ID for a user"""
        db = SessionLocal()
        try:
            stmt = update(RefreshToken).where(
                RefreshToken.id == session_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)
            ).values(revoked_at=datetime.now(timezone.utc))
            res = db.execute(stmt)
            db.commit()
            return res.rowcount > 0
        finally:
            db.close()

    @staticmethod
    def get_refresh_token_by_id(session_id: int) -> Optional[Dict[str, Any]]:
        """Get refresh token record by session ID"""
        db = SessionLocal()
        try:
            rt = db.get(RefreshToken, session_id)
            return model_to_dict(rt) if rt else None
        finally:
            db.close()

    @staticmethod
    def count_recent_failed_logins(email: str, minutes: int = 15) -> int:
        """Count login_failed events for target email within the last N minutes using exact match"""
        if not email:
            return 0
        clean_email = email.strip().lower()
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            count = db.query(AuthAuditLog).filter(
                AuthAuditLog.event_type == "login_failed",
                AuthAuditLog.created_at >= cutoff,
                AuthAuditLog.email == clean_email
            ).count()
            return count
        finally:
            db.close()

    @staticmethod
    def count_recent_failed_logins_by_ip(ip_address: str, minutes: int = 15) -> int:
        """Count login_failed events for target IP address within the last N minutes"""
        if not ip_address:
            return 0
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            count = db.query(AuthAuditLog).filter(
                AuthAuditLog.event_type == "login_failed",
                AuthAuditLog.created_at >= cutoff,
                AuthAuditLog.ip_address == ip_address
            ).count()
            return count
        finally:
            db.close()

    @staticmethod
    def revoke_other_user_sessions(user_id: int, current_token_hash: Optional[str]) -> int:
        """Revoke all active refresh token sessions for a user EXCEPT the current session"""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            query = db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None)
            )
            if current_token_hash:
                query = query.filter(RefreshToken.token_hash != current_token_hash)
            rows = query.all()
            for r in rows:
                r.revoked_at = now
            db.commit()
            return len(rows)
        finally:
            db.close()

    # ===== AUDIT LOGGING METHODS =====
    @staticmethod
    def log_auth_event(
        event_type: str,
        user_id: Optional[int] = None,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        detail: Optional[str] = None
    ):
        """Fire-and-forget auth audit logging with structured email/subject field"""
        clean_email = email.strip().lower() if email else None
        db = SessionLocal()
        try:
            log_entry = AuthAuditLog(
                user_id=user_id,
                email=clean_email,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                detail=detail
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[AuditLog Error] Failed to log auth event '{event_type}': {e}")
        finally:
            db.close()

    @staticmethod
    def get_admin_audit_logs(
        page: int = 1,
        per_page: int = 20,
        event_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch paginated auth_audit_log entries with optional filtering"""
        db = SessionLocal()
        try:
            query = db.query(AuthAuditLog)
            if event_type:
                query = query.filter(AuthAuditLog.event_type == event_type)
            if start_date:
                try:
                    s_dt = datetime.fromisoformat(start_date.replace(" ", "T"))
                    if s_dt.tzinfo is None:
                        s_dt = s_dt.replace(tzinfo=timezone.utc)
                    query = query.filter(AuthAuditLog.created_at >= s_dt)
                except Exception:
                    pass
            if end_date:
                try:
                    e_dt = datetime.fromisoformat(end_date.replace(" ", "T"))
                    if e_dt.tzinfo is None:
                        e_dt = e_dt.replace(tzinfo=timezone.utc)
                    query = query.filter(AuthAuditLog.created_at <= e_dt)
                except Exception:
                    pass

            total = query.count()
            offset = (page - 1) * per_page
            rows = query.order_by(AuthAuditLog.created_at.desc()).offset(offset).limit(per_page).all()
            logs = [model_to_dict(r) for r in rows]
            total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1

            return {
                "logs": logs,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
        finally:
            db.close()

    # ===== 2FA METHODS =====
    @staticmethod
    def set_user_2fa_secret(user_id: int, secret: Optional[str], enabled: bool = False):
        """Update user 2FA secret (encrypted at rest with authenticated encryption) and enabled status (M1)"""
        from app.auth.utils import encrypt_totp_secret
        enc_secret = encrypt_totp_secret(secret) if secret else None
        db = SessionLocal()
        try:
            update_values = {
                "two_factor_secret": enc_secret,
                "two_factor_enabled": enabled
            }
            if not enabled:
                update_values["last_totp_step"] = None
            stmt = update(User).where(User.id == user_id).values(**update_values)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_totp_secret(user_id: int) -> Optional[str]:
        """Retrieve and decrypt the user's TOTP secret at runtime (M1)"""
        from app.auth.utils import decrypt_totp_secret
        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if user and user.two_factor_secret:
                return decrypt_totp_secret(user.two_factor_secret)
            return None
        finally:
            db.close()

    @staticmethod
    def update_user_last_totp_step(user_id: int, step: int):
        """Record the last used TOTP time step to prevent replay attacks (M1)"""
        db = SessionLocal()
        try:
            stmt = update(User).where(User.id == user_id).values(last_totp_step=step)
            db.execute(stmt)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def count_recent_failed_2fa(user_id: int, minutes: int = 15) -> int:
        """Count failed 2FA verification attempts for target user in the last N minutes (M1)"""
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            return db.query(AuthAuditLog).filter(
                AuthAuditLog.user_id == user_id,
                AuthAuditLog.event_type == "2fa_failed",
                AuthAuditLog.created_at >= cutoff
            ).count()
        finally:
            db.close()

    @staticmethod
    def save_user_backup_codes(user_id: int, code_hashes: List[str]):
        """Replace user's 2FA backup code hashes"""
        from app.db.models import TwoFactorBackupCode
        db = SessionLocal()
        try:
            db.query(TwoFactorBackupCode).filter(TwoFactorBackupCode.user_id == user_id).delete()
            for ch in code_hashes:
                bc = TwoFactorBackupCode(user_id=user_id, code_hash=ch)
                db.add(bc)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def verify_and_consume_backup_code(user_id: int, code: str) -> bool:
        """Atomically verify and consume a backup code using keyed hash and legacy fallback (M1, N5)."""
        from app.db.models import TwoFactorBackupCode
        from app.auth.utils import hash_backup_code, legacy_hash_backup_code, legacy_secret_key_hash_backup_code, legacy_pepper_hash_backup_code
        clean_code = code.strip()
        keyed_h = hash_backup_code(clean_code)
        legacy_pepper_h = legacy_pepper_hash_backup_code(clean_code)
        secret_key_h = legacy_secret_key_hash_backup_code(clean_code)
        legacy_h = legacy_hash_backup_code(clean_code)
        now = datetime.now(timezone.utc)
        db = SessionLocal()
        try:
            # Atomic single-statement consumption: only updates if used_at IS NULL
            stmt = (
                update(TwoFactorBackupCode)
                .where(
                    TwoFactorBackupCode.user_id == user_id,
                    TwoFactorBackupCode.code_hash.in_([keyed_h, legacy_pepper_h, secret_key_h, legacy_h]),
                    TwoFactorBackupCode.used_at.is_(None)
                )
                .values(used_at=now)
            )
            res = db.execute(stmt)
            db.commit()
            return res.rowcount > 0
        finally:
            db.close()

    @staticmethod
    def cleanup_legacy_tokens():
        """Perform one-time cleanup of legacy unhashed or expired reset and verification tokens (N2)."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            users = db.query(User).filter(
                (User.reset_password_token != None) | (User.verification_token != None)
            ).all()
            for user in users:
                if user.reset_password_token:
                    is_valid_hash = (
                        len(user.reset_password_token) == 64 and
                        all(c in "0123456789abcdefABCDEF" for c in user.reset_password_token)
                    )
                    is_expired = False
                    if user.reset_password_token_expiry:
                        exp = user.reset_password_token_expiry
                        if exp.tzinfo is None:
                            exp = exp.replace(tzinfo=timezone.utc)
                        is_expired = exp < now
                    if not is_valid_hash or is_expired:
                        user.reset_password_token = None
                        user.reset_password_token_expiry = None

                if user.verification_token:
                    is_valid_hash = (
                        len(user.verification_token) == 64 and
                        all(c in "0123456789abcdefABCDEF" for c in user.verification_token)
                    )
                    is_expired = False
                    if user.verification_token_expiry:
                        exp = user.verification_token_expiry
                        if exp.tzinfo is None:
                            exp = exp.replace(tzinfo=timezone.utc)
                        is_expired = exp < now
                    if not is_valid_hash or is_expired:
                        user.verification_token = None
                        user.verification_token_expiry = None

            db.commit()
        finally:
            db.close()

    @staticmethod
    def identify_broken_2fa_users() -> List[Dict[str, Any]]:
        """Identify users whose 2FA secret cannot be decrypted under current keys (N5).
        Returns user info and safe diagnostics without exposing secrets.
        """
        from app.auth.utils import decrypt_totp_secret
        from app.db.models import TwoFactorBackupCode
        db = SessionLocal()
        broken = []
        try:
            users = db.query(User).filter(
                User.two_factor_enabled == True,
                User.two_factor_secret.is_not(None)
            ).all()
            for u in users:
                decrypted = decrypt_totp_secret(u.two_factor_secret)
                if not decrypted:
                    has_backup = db.query(TwoFactorBackupCode).filter(
                        TwoFactorBackupCode.user_id == u.id,
                        TwoFactorBackupCode.used_at.is_(None)
                    ).count() > 0
                    broken.append({
                        "user_id": u.id,
                        "email": u.email,
                        "has_backup_codes": has_backup
                    })
            return broken
        finally:
            db.close()



