from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.auth.utils import get_current_user
from app.services.email_service import EmailService
from app.auth.models import DBManager

router = APIRouter(prefix="/feedback", tags=["feedback"])

class FeedbackSubmitRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=10000)

@router.post("/submit")
async def submit_feedback(
    request: FeedbackSubmitRequest,
    current_user: dict = Depends(get_current_user)
):
    """Persist feedback in Neon and attempt configured email delivery."""
    if not request.feedback.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback content cannot be empty."
        )
    
    feedback_id = await run_in_threadpool(DBManager.create_feedback, current_user["id"], request.feedback)
    if not feedback_id:
        raise HTTPException(503, 'Feedback could not be saved. Please retry.')

    success = await run_in_threadpool(
        EmailService.send_feedback_email,
        user_email=current_user["email"],
        user_name=current_user["full_name"],
        feedback_text=request.feedback
    )
    
    return {"message": "Feedback submitted successfully. Thank you!"}
