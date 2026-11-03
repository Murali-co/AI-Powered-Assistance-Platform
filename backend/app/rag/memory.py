from typing import List, Dict, Any, Optional
from app.db.session import SessionLocal
from app.db.models import ChatMessage


class ChatMemory:
    @staticmethod
    def add_message(session_id: str, user_id: int, role: str, content: str):
        db = SessionLocal()
        try:
            msg = ChatMessage(session_id=session_id, user_id=user_id, role=role, content=content)
            db.add(msg)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_messages(session_id: str, user_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
        db = SessionLocal()
        try:
            query = db.query(ChatMessage).filter(ChatMessage.session_id == session_id)
            if user_id is not None:
                query = query.filter(ChatMessage.user_id == user_id)
            rows = query.order_by(ChatMessage.id.desc()).limit(limit).all()
            messages = [{"role": r.role, "content": r.content} for r in reversed(rows)]
            return messages
        finally:
            db.close()

    @staticmethod
    def clear_session(session_id: str, user_id: Optional[int] = None):
        db = SessionLocal()
        try:
            query = db.query(ChatMessage).filter(ChatMessage.session_id == session_id)
            if user_id is not None:
                query = query.filter(ChatMessage.user_id == user_id)
            query.delete()
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_sessions(user_id: int) -> List[str]:
        db = SessionLocal()
        try:
            rows = db.query(ChatMessage.session_id).filter(ChatMessage.user_id == user_id).distinct().all()
            return [r[0] for r in rows]
        finally:
            db.close()
