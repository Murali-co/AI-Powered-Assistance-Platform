from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.auth.utils import get_current_user
from app.auth.models import DBManager

router = APIRouter(prefix="/notifications", tags=["notifications"])

class PushTokenRequest(BaseModel):
    token: str
    device_type: Optional[str] = "web"

@router.get("")
async def get_user_notifications(
    only_unread: bool = False,
    current_user: dict = Depends(get_current_user)
):
    return DBManager.get_notifications(current_user["id"], only_unread=only_unread)

@router.post("/read/{notification_id}")
async def mark_notification_as_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user)
):
    DBManager.mark_notification_read(notification_id, current_user["id"])
    return {"message": "Notification marked as read."}

@router.post("/read-all")
async def mark_all_notifications_as_read(
    current_user: dict = Depends(get_current_user)
):
    DBManager.mark_all_notifications_read(current_user["id"])
    return {"message": "All notifications marked as read."}

@router.post("/push-token")
async def save_push_token(
    req: PushTokenRequest,
    current_user: dict = Depends(get_current_user)
):
    DBManager.save_push_token(current_user["id"], req.token, req.device_type)
    return {"message": "Push token registered"}
