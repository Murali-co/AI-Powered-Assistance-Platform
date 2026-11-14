import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.auth.utils import get_current_user, get_client_ip
from app.auth.models import DBManager
from app.models.schemas import ChangePasswordRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

class UserSettingsUpdate(BaseModel):
    full_name: Optional[str] = None
    email_notifications: Optional[bool] = None
    daily_digest: Optional[bool] = None
    scrape_frequency_hours: Optional[int] = None

class UserSettingsResponse(BaseModel):
    id: int
    email: str
    full_name: str
    email_notifications: bool = True
    daily_digest: bool = True
    scrape_frequency_hours: int = 12

    model_config = ConfigDict(from_attributes=True)

@router.get("/profile", response_model=UserSettingsResponse)
def get_settings(current_user: dict = Depends(get_current_user)):
    """Get current user settings (H5: sync def handler)"""
    user = DBManager.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "email_notifications": user.get("email_notifications", True),
        "daily_digest": user.get("daily_digest", True),
        "scrape_frequency_hours": user.get("scrape_frequency_hours", 12)
    }

@router.patch("/profile")
def update_settings(
    updates: UserSettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update user settings (H5: sync def handler)"""
    try:
        user_id = current_user["id"]
        
        if updates.full_name:
            DBManager.update_user_full_name(user_id, updates.full_name)
        
        if updates.email_notifications is not None:
            DBManager.update_user_preference(user_id, "email_notifications", updates.email_notifications)
        
        if updates.daily_digest is not None:
            DBManager.update_user_preference(user_id, "daily_digest", updates.daily_digest)
        
        if updates.scrape_frequency_hours is not None:
            if updates.scrape_frequency_hours < 1 or updates.scrape_frequency_hours > 168:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Scrape frequency must be between 1 and 168 hours"
                )
            DBManager.update_user_preference(user_id, "scrape_frequency_hours", updates.scrape_frequency_hours)
        
        return {
            "message": "Settings updated successfully",
            "user": {
                "id": user_id,
                "full_name": updates.full_name or current_user["full_name"],
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update settings for user {current_user.get('id')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )

@router.post("/preferences/notification-frequency")
def set_notification_frequency(
    enabled: bool,
    current_user: dict = Depends(get_current_user)
):
    """Enable/disable email notifications (H5: sync def handler)"""
    DBManager.update_user_preference(current_user["id"], "email_notifications", enabled)
    return {"message": f"Email notifications {'enabled' if enabled else 'disabled'}"}

@router.post("/preferences/scrape-frequency")
def set_scrape_frequency(
    hours: int,
    current_user: dict = Depends(get_current_user)
):
    """Set job scraping frequency (hours) (H5: sync def handler)"""
    if hours < 1 or hours > 168:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Frequency must be between 1 and 168 hours (1 week max)"
        )
    DBManager.update_user_preference(current_user["id"], "scrape_frequency_hours", hours)
    return {"message": f"Scraping frequency set to {hours} hours"}

@router.post("/password/change")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user)
):
    """
    Change user password (H5: sync def handler, H6, N3).
    Accepts current_password and new_password exclusively in the JSON request body.
    Enforces minimum 10 and maximum 128 characters.
    Revokes all existing refresh token sessions across all devices.
    Issues a fresh session token pair for the current client.
    """
    from app.auth.utils import verify_password, get_password_hash
    from app.auth.router import issue_tokens_and_set_cookies
    
    curr_pwd = payload.current_password
    new_pwd = payload.new_password
    
    user = DBManager.get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not verify_password(curr_pwd, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    if curr_pwd == new_pwd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be the same as current password"
        )
    
    hashed_new_password = get_password_hash(new_pwd)
    DBManager.update_password(current_user["id"], hashed_new_password)
    
    # H6: Revoke ALL existing refresh sessions across all devices
    DBManager.revoke_all_user_refresh_tokens(current_user["id"])
    
    # Issue fresh tokens for the current device
    access_token, _, _ = issue_tokens_and_set_cookies(
        user["id"], user["email"], request, response
    )
    
    DBManager.log_auth_event(
        "password_changed",
        user_id=user["id"],
        email=user["email"],
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail="Password changed successfully; existing sessions revoked, new session issued."
    )
    
    return {
        "message": "Password changed successfully",
        "access_token": access_token,
        "token_type": "bearer"
    }
