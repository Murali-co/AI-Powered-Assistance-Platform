from typing import List, Dict, Any
from sqlalchemy import func
from app.db.session import SessionLocal
from app.db.models import ChatMessage


class ChatMemory:
    @staticmethod
    def add_message(session_id: str, user_id: int, role: str, content: str) -> int:
        db = SessionLocal()
        try:
            msg = ChatMessage(session_id=session_id, user_id=user_id, role=role, content=content)
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return msg.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_messages(session_id: str, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            query = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user_id
            )
            rows = query.order_by(ChatMessage.id.desc()).limit(limit).all()
            messages = [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "role": r.role,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in reversed(rows)
            ]
            return messages
        finally:
            db.close()

    @staticmethod
    def clear_session(session_id: str, user_id: int) -> int:
        db = SessionLocal()
        try:
            count = db.query(ChatMessage).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user_id
            ).delete()
            db.commit()
            return count
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_sessions(user_id: int) -> List[str]:
        db = SessionLocal()
        try:
            rows = (
                db.query(ChatMessage.session_id)
                .filter(ChatMessage.user_id == user_id)
                .group_by(ChatMessage.session_id)
                .order_by(func.max(ChatMessage.id).desc())
                .all()
            )
            return [r[0] for r in rows]
        finally:
            db.close()

    @staticmethod
    def session_exists(session_id: str, user_id: int) -> bool:
        db = SessionLocal()
        try:
            row = db.query(ChatMessage.id).filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user_id
            ).first()
            return row is not None
        finally:
            db.close()
