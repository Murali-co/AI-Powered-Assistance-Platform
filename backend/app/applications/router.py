import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Response, Body, Request
from fastapi.responses import FileResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.models.schemas import ApplicationSubmitRequest, ApplicationHistoryOut, ApplicationPackageResponse
from app.db.session import SessionLocal
from app.db.models import ApplicationStatusHistory
from app.applications.generator import ApplicationGenerator
from app.jobs.matcher import JobMatcher
from app.utils.bg_jobs import create_job, update_job
from app.utils.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apply", tags=["applications"])

class UpdateStatusPayload(BaseModel):
    status: Optional[str] = None
    new_status: Optional[str] = None

async def run_apply_generation_task(job_id: str, bg_job_id: str, user_id: int, full_name: str):
    try:
        update_job(bg_job_id, "processing")
        
        # Generate application package
        package = await ApplicationGenerator.generate_package(
            user_id=user_id,
            job_id=job_id,
            full_name=full_name
        )
        
        update_job(bg_job_id, "completed", result=package)
    except __import__('asyncio').CancelledError:
        logger.warning("Generation task %s was cancelled due to server shutdown.", bg_job_id)
        update_job(bg_job_id, "failed", error="Server shutdown during generation.")
        raise
    except Exception as e:
        logger.exception("Error generating application package for job %s: %s", job_id, e)
        update_job(bg_job_id, "failed", error="Failed to generate application package. Please retry.")

@router.post("/generate/{job_id}")
@limiter.limit("10/minute")
async def generate_application(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    # Verify job exists in ChromaDB
    jobs_collection = JobMatcher.get_collection()
    job_result = jobs_collection.get(ids=[job_id])
    if not job_result or not job_result["ids"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job listing not found."
        )
        
    bg_job_id = create_job(user_id=current_user["id"])
    background_tasks.add_task(
        run_apply_generation_task,
        job_id,
        bg_job_id,
        current_user["id"],
        current_user["full_name"]
    )
    
    return {"job_id": bg_job_id, "status": "pending"}

@router.post("/submit")
async def record_submission(
    request: ApplicationSubmitRequest,
    current_user: dict = Depends(get_current_user)
):
    # 1. Fetch Job Info with manual logging fallback
    job_title = request.title
    company = request.company
    location = request.location
    job_url = request.job_url
    
    if not job_title or not company:
        jobs_collection = JobMatcher.get_collection()
        try:
            job_result = jobs_collection.get(ids=[request.job_id])
        except Exception:
            job_result = None
            
        if not job_result or not job_result["ids"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job listing not found. Cannot log submission."
            )
            
        job_meta = job_result["metadatas"][0]
        job_title = job_title or job_meta.get("title", "Unknown Role")
        company = company or job_meta.get("company", "Unknown Company")
        location = location or job_meta.get("location")
        job_url = job_url or job_meta.get("job_url")
        
    # 2. Extract or fallback cover letter and resume bullets
    cover_letter = request.cover_letter or "Applied with tailored cover letter."
    
    import json
    if isinstance(request.resume_bullets, list):
        resume_bullets = json.dumps(request.resume_bullets)
    elif isinstance(request.resume_bullets, str):
        resume_bullets = request.resume_bullets
    else:
        resume_bullets = "[]"
    
    app_id = str(uuid.uuid4())
    applied_at_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    DBManager.add_application(
        app_id=app_id,
        user_id=current_user["id"],
        job_id=request.job_id,
        job_title=job_title,
        company=company,
        applied_at=applied_at_str,
        status=request.status,
        cover_letter=cover_letter,
        resume_bullets=resume_bullets,
        notes=request.notes or "",
        location=location,
        job_url=job_url,
        resume_version_id=request.resume_version_id,
        tone=request.tone,
    )
    
    return {"message": "Application logged successfully.", "application_id": app_id}

@router.get("/history", response_model=List[ApplicationHistoryOut])
async def get_history(current_user: dict = Depends(get_current_user)):
    history = DBManager.get_applications(current_user["id"])
    
    formatted = []
    for item in history:
        import json
        try:
            bullets = json.loads(item["resume_bullets"])
            if not isinstance(bullets, list):
                bullets = [str(bullets)]
        except Exception:
            bullets = [item["resume_bullets"]] if item["resume_bullets"] else []
            
        formatted.append(
            ApplicationHistoryOut(
                id=item["id"],
                user_id=item["user_id"],
                job_id=item["job_id"],
                job_title=item["job_title"],
                company=item["company"],
                applied_at=str(item["applied_at"]),
                status=item["status"],
                cover_letter=item["cover_letter"],
                resume_bullets=bullets,
                notes=item["notes"],
                location=item.get("location"),
                job_url=item.get("job_url"),
                resume_version_id=item.get("resume_version_id"),
                tone=item.get("tone"),
                status_history=DBManager.get_application_status_history(item["id"])
            )
        )
    return formatted

@router.get("/export/{application_id}/pdf")
async def export_application_pdf(
    application_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Export application (cover letter + resume bullets) as PDF"""
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        
        # Fetch application record
        application = DBManager.get_application(application_id, current_user["id"])
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )
        
        # Parse resume bullets
        import json
        try:
            bullets = json.loads(application["resume_bullets"])
            if isinstance(bullets, str):
                bullets = [bullets]
        except (json.JSONDecodeError, ValueError, TypeError):
            bullets = [application["resume_bullets"]] if application["resume_bullets"] else []
        
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor='#1a1a1a',
            spaceAfter=12
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor='#2a2a2a',
            spaceAfter=6
        )
        
        # Build content
        content = []
        
        # Header
        content.append(Paragraph(
            f"{application['job_title']} at {application['company']}",
            title_style
        ))
        content.append(Spacer(1, 0.2*inch))
        
        # Cover Letter
        content.append(Paragraph("Cover Letter", heading_style))
        content.append(Paragraph(application["cover_letter"], styles['BodyText']))
        content.append(Spacer(1, 0.2*inch))
        
        # Resume Bullets
        content.append(Paragraph("Tailored Resume Bullets", heading_style))
        for i, bullet in enumerate(bullets, 1):
            bullet_text = f"<b>{i}.</b> {bullet}"
            content.append(Paragraph(bullet_text, styles['BodyText']))
            content.append(Spacer(1, 0.1*inch))
        
        # Notes if any
        if application.get("notes"):
            content.append(Spacer(1, 0.2*inch))
            content.append(Paragraph("Notes", heading_style))
            content.append(Paragraph(application["notes"], styles['BodyText']))
        
        # Build PDF
        doc.build(content)
        pdf_buffer.seek(0)
        
        # Return as file download
        filename = f"{application['company']}_{application['job_title'].replace(' ', '_')}.pdf"
        return Response(
            content=pdf_buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"PDF export error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF export failed"
        )

@router.get("/{application_id}/status-history")
async def get_application_status_history(
    application_id: str,
    current_user: dict = Depends(get_current_user)
):
    application = DBManager.get_application(application_id, current_user["id"])
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return DBManager.get_application_status_history(application_id)

@router.patch("/{application_id}/status")
@router.put("/{application_id}/status")
async def update_application_status(
    application_id: str,
    new_status: Optional[str] = None,
    payload: Optional[UpdateStatusPayload] = Body(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Update application status (applied, interview_scheduled, offered, rejected)
    """
    target_status = new_status or (payload.new_status if payload else None) or (payload.status if payload else None)
    if not target_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be provided via query parameter 'new_status' or request body {'status': ...}"
        )

    valid_statuses = ["applied", "interviewing", "interview_scheduled", "offered", "rejected", "accepted"]
    
    if target_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Get and verify application ownership
    application = DBManager.get_application(application_id, current_user["id"])
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    try:
        # Update status in database
        DBManager.update_application_status(application_id, target_status)

        return {
            "message": "Application status updated",
            "application_id": application_id,
            "status": target_status,
            "new_status": target_status
        }
    except Exception as e:
        logger.exception(f"Failed to update application status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update status"
        )

