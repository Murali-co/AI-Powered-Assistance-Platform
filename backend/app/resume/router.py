from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, HTTPException, status, Request
from typing import Dict, Any, List, Optional
from starlette.concurrency import run_in_threadpool
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.resume.parser import ResumeParser
from app.resume.cleaner import ResumeCleaner
from app.resume.extractor import SkillExtractor
from app.vector_db.profile_store import ProfileStore
from app.llm.skill_gap import SkillGapAnalyzer
from app.llm.cover_letter import CoverLetterGenerator
from app.llm.ollama_client import OllamaClient
from app.models.schemas import SkillGapRequest, CoverLetterRequest, CoverLetterResponse, ResumeTailorRequest, ResumeTailorResponse
from app.db.models import ResumeVersion
from app.utils.bg_jobs import create_job, update_job, get_job
from app.jobs.matcher import JobMatcher
from app.llm.resume_tailor import ResumeTailorEngine
from app.utils.limiter import limiter
from app.db.session import SessionLocal
from pydantic import BaseModel
import os
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]
ALLOWED_EXTENSIONS = [".pdf", ".docx"]

async def _trigger_role_based_live_search(user_id: int, roles: List[str], location: str = "Any", hours_old: int = 48) -> List[str]:
    """Trigger a live scrape using resume-derived roles and persist the first role as the user's default criteria."""
    roles = [str(role).strip() for role in roles if str(role).strip()]
    if not roles:
        return []

    primary_role = roles[0]
    if not DBManager.get_criteria(user_id):
        DBManager.save_criteria(
            user_id=user_id,
            title=primary_role,
            location=location,
            is_remote=location.lower() == "remote",
            job_type=None,
            hours_old=hours_old,
        )

    scraped_roles: List[str] = []
    for role in roles[:3]:
        try:
            jobs = await run_in_threadpool(
                JobScraper.scrape,
                search_term=role,
                location=location,
                results_wanted=8,
                hours_old=hours_old,
            )
            if jobs:
                JobMatcher.upsert_jobs(jobs)
                scraped_roles.append(role)
        except Exception as exc:
            print(f"Resume-triggered live search skipped for '{role}': {exc}")
    return scraped_roles


async def _run_role_fetch_task(job_id: str, user_id: int, role: str, location: str = "Any", hours_old: int = 720):
    try:
        update_job(job_id, "processing")
        jobs = await run_in_threadpool(JobScraper.scrape, search_term=role, location=location, results_wanted=10, hours_old=hours_old)
        if jobs:
            await run_in_threadpool(JobMatcher.upsert_jobs, jobs)
        matched = await run_in_threadpool(JobMatcher.match_jobs_for_user, user_id, limit=10, hours_old=hours_old)
        update_job(job_id, "completed", result={
            "role": role,
            "location": location,
            "jobs_found": len(jobs),
            "matched_jobs": len(matched),
            "jobs": matched[:10],
        })
    except Exception as exc:
        update_job(job_id, "failed", error=str(exc))


async def run_analysis_task(job_id: str, user_id: int, target_role: str):
    try:
        update_job(job_id, "processing")
        
        # 1. Fetch user profile
        profile = ProfileStore.get_profile(user_id)
        if not profile or not profile.get("resume_text"):
            raise ValueError("No resume uploaded for user. Please upload a resume first.")

        skills = profile.get("skills", [])
        resume_text = profile.get("resume_text", "")
        
        # 2. Run Skill Gap Analysis (Ollama)
        gap_results = await SkillGapAnalyzer.analyze(skills, target_role)
        
        # 3. Generate baseline Cover Letter (Ollama)
        cover_letter = await CoverLetterGenerator.generate(resume_text, target_role, tone="formal")

        suggested_roles = [target_role]
        if isinstance(gap_results, dict):
            for value in [gap_results.get("missing_skills", []), gap_results.get("recommendations", [])]:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            suggested_roles.append(item.strip())
        if len(suggested_roles) < 3:
            suggested_roles.extend(["Software Engineer", "Backend Developer", "Full Stack Developer"])

        fetch_job_ids = []
        for role in suggested_roles[:3]:
            fetch_job_id = create_job(user_id=user_id)
            fetch_job_ids.append(fetch_job_id)
            asyncio.create_task(_run_role_fetch_task(fetch_job_id, user_id, role, location="Any", hours_old=720))

        result = {
            "skill_gap": gap_results,
            "cover_letter": cover_letter,
            "target_role": target_role,
            "suggested_roles": suggested_roles[:3],
            "fetch_job_ids": fetch_job_ids,
        }
        
        update_job(job_id, "completed", result=result)
    except __import__('asyncio').CancelledError:
        print(f"Resume analysis task {job_id} was cancelled due to server shutdown.")
        update_job(job_id, "failed", error="Server shutdown during analysis.")
        raise
    except Exception as e:
        print(f"Error in background resume analysis task: {e}")
        update_job(job_id, "failed", error=str(e))

def validate_file_signature(file_bytes: bytes, ext: str) -> bool:
    """Validate file magic bytes / signature against extension (M7)."""
    if ext == ".pdf":
        return file_bytes.startswith(b"%PDF")
    if ext == ".docx":
        # Standard ZIP archives (DOCX is OpenXML ZIP) start with PK\x03\x04
        return file_bytes.startswith(b"PK")
    return False

def _process_resume_pipeline(file_bytes: bytes, filename: str, user_id: int) -> Dict[str, Any]:
    """Synchronous CPU/DB work for resume parsing, offloaded to threadpool (H5)."""
    raw_text = ResumeParser.parse(file_bytes, filename)
    if not raw_text or not raw_text.strip():
        raise ValueError("Extracted text is empty. The file may be scanned, image-only, empty, or corrupted.")
        
    cleaned_sections = ResumeCleaner.segment_sections(raw_text)
    
    # Re-assemble cleaned text
    cleaned_full_text = "\n\n".join([f"[{sec.upper()}]\n{content}" for sec, content in cleaned_sections.items() if content])
    if not cleaned_full_text.strip():
        cleaned_full_text = raw_text.strip()
    
    # Extract Skills
    extracted_skills_data = SkillExtractor.extract_skills(cleaned_full_text, cleaned_sections)
    skills_list = [item["skill"] for item in extracted_skills_data]
    
    # Save to vector DB
    ProfileStore.store_profile(
        user_id=user_id,
        resume_text=cleaned_full_text,
        skills=skills_list
    )
    
    # Save historical version
    DBManager.save_resume_version(
        user_id=user_id,
        resume_text=cleaned_full_text,
        label=f"Resume Upload: {filename}"
    )
    
    return {
        "skills": skills_list,
        "text_preview": cleaned_full_text[:1000] + ("..." if len(cleaned_full_text) > 1000 else "")
    }

@router.post("/upload")
@limiter.limit("5/minute")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # 1. Bounded chunk-based reading (M7: prevent memory exhaustion from oversized payloads)
    CHUNK_SIZE = 64 * 1024  # 64KB chunks
    total_bytes = bytearray()
    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total_bytes.extend(chunk)
            if len(total_bytes) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File size exceeds the {MAX_FILE_SIZE // (1024 * 1024)}MB limit."
                )
    finally:
        await file.close()
    file_bytes = bytes(total_bytes)

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    # 2. Validate MIME Type and Extension
    filename = file.filename or ""
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED_EXTENSIONS or file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only PDF and DOCX files are allowed."
        )

    # 3. File signature / magic-byte verification (M7)
    if not validate_file_signature(file_bytes, ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match the file extension signature. Please upload a valid PDF or DOCX file."
        )

    # 4. Offload heavy parsing & extraction to thread pool (H5)
    try:
        proc_result = await run_in_threadpool(
            _process_resume_pipeline,
            file_bytes,
            filename,
            current_user["id"]
        )
        return {
            "message": "Resume uploaded and processed successfully.",
            "skills": proc_result["skills"],
            "text_preview": proc_result["text_preview"]
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err)
        )
    except Exception as e:
        logger.exception(f"Failed to process resume: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process resume"
        )

@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze_resume(
    request: Request,
    req_body: SkillGapRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    # Check if profile exists
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )

    # Create job id and spin off background task
    job_id = create_job(user_id=current_user["id"])
    background_tasks.add_task(
        run_analysis_task,
        job_id,
        current_user["id"],
        req_body.target_role
    )
    
    return {"job_id": job_id, "status": "pending"}

@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resume profile found. Please upload a resume first."
        )
    return profile

@router.post("/suggest-roles")
@limiter.limit("5/minute")
async def suggest_roles(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Automatically suggests top 3-5 job roles based on the uploaded resume.
    Call this right after /upload succeeds.
    """
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No resume uploaded.")
    
    resume_text = profile["resume_text"][:3000]  # truncate to save tokens
    skills = profile.get("skills", [])
    
    prompt = f"""
You are a career expert. Based on this resume, suggest the TOP 5 most suitable job roles for this candidate.

Resume:
{resume_text}

Extracted Skills: {', '.join(skills[:20]) if skills else 'Not extracted yet'}

Return ONLY a JSON array of exactly 5 role strings. No explanation, no markdown.
Example: ["Software Engineer", "Backend Developer", "Python Developer", "API Engineer", "Data Engineer"]
"""
    
    try:
        result = await OllamaClient.generate(prompt, format="json", think=False)
        result = result.strip()
        # Clean markdown fences if present
        if "```" in result:
            result = result.split("```")[1].replace("json", "").strip()
        roles = json.loads(result)
        if not isinstance(roles, list):
            raise ValueError("Not a list")
        roles = [str(r).strip() for r in roles[:5] if r]
    except Exception as e:
        print(f"Error suggesting roles: {e}")
        # Fallback based on skills
        roles = ["Software Engineer", "Backend Developer", "Full Stack Developer",
                 "Python Developer", "API Developer"]

    try:
        criteria = DBManager.get_criteria(current_user["id"]) or {}
        location = criteria.get("location") or "Any"
        hours_old = criteria.get("hours_old") or 48
        profile = ProfileStore.get_profile(current_user["id"]) or {}
        ProfileStore.store_profile(
            user_id=current_user["id"],
            resume_text=profile.get("resume_text", ""),
            skills=profile.get("skills", []),
            metadata={"suggested_roles": roles}
        )
        await _trigger_role_based_live_search(current_user["id"], roles, location=location, hours_old=hours_old)
        DBManager.save_criteria(
            user_id=current_user["id"],
            title=roles[0],
            location=location,
            is_remote=location.lower() == "remote",
            job_type=criteria.get("job_type"),
            hours_old=hours_old,
        )
    except Exception as exc:
        print(f"Resume-role live search could not run: {exc}")
    
    return {"suggested_roles": roles}

@router.post("/cover-letter", response_model=CoverLetterResponse)
@limiter.limit("5/minute")
async def generate_cover_letter_tone(
    request: Request,
    req_body: CoverLetterRequest,
    current_user: dict = Depends(get_current_user)
):
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )
    text = await CoverLetterGenerator.generate(
        resume_text=profile["resume_text"],
        target_role=req_body.target_role,
        company_name=req_body.company_name,
        tone=req_body.tone or "formal"
    )
    text = text.replace("[Your Name]", current_user["full_name"])
    text = text.replace("[Candidate Name]", current_user["full_name"])
    return {"cover_letter": text}

@router.post("/tailor", response_model=ResumeTailorResponse)
@limiter.limit("5/minute")
async def tailor_resume(
    request: Request,
    req_body: ResumeTailorRequest,
    current_user: dict = Depends(get_current_user)
):
    # 1. Fetch user profile
    profile = ProfileStore.get_profile(current_user["id"])
    if not profile or not profile.get("resume_text"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please upload a resume first."
        )

    # 2. Fetch target job from vector db or use supplied job description
    job_desc = req_body.job_description
    if not job_desc:
        if not req_body.job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either job_id or job_description must be provided."
            )
        collection = JobMatcher.get_collection()
        job_data = collection.get(ids=[str(req_body.job_id)])
        if not job_data or not job_data["ids"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target job listing not found in local database."
            )
        job_desc = job_data["documents"][0]

    # 3. Call LLM Tailoring Engine
    tailored_result = await ResumeTailorEngine.tailor(profile["resume_text"], job_desc)
    return tailored_result

@router.post("/select-version")
async def select_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume version not found")

    profile = ProfileStore.get_profile(current_user["id"])
    if profile is None:
        profile = {}
    ProfileStore.store_profile(user_id=current_user["id"], resume_text=version["resume_text"], skills=profile.get("skills", []))
    return {"message": "Resume version selected", "version_id": version_id}

class ProfileEditRequest(BaseModel):
    skills: List[str]
    resume_text: str

@router.post("/profile/edit")
async def edit_profile(
    req: ProfileEditRequest,
    current_user: dict = Depends(get_current_user)
):
    ProfileStore.store_profile(
        user_id=current_user["id"],
        resume_text=req.resume_text,
        skills=req.skills
    )
    DBManager.save_resume_version(
        user_id=current_user["id"],
        resume_text=req.resume_text,
        label="Manual Edit via Dashboard"
    )
    return {"message": "Profile updated successfully."}

@router.get("/versions")
async def get_resume_versions(current_user: dict = Depends(get_current_user)):
    return DBManager.get_resume_versions(current_user["id"])


class CreateResumeVersionRequest(BaseModel):
    version_label: str
    target_role: Optional[str] = "General"
    resume_text: Optional[str] = None


@router.post("/versions/create")
async def create_resume_version(
    req: CreateResumeVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Creates a new named resume version targeted at a specific role.
    If resume_text is omitted, initializes from user's current verified career profile.
    """
    user_id = current_user["id"]
    text_to_save = req.resume_text
    if not text_to_save:
        p = ProfileStore.get_profile(user_id) or {}
        text_to_save = p.get("resume_text", "")
        if not text_to_save:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No base resume found. Please provide resume text or upload an initial resume."
            )

    version_id = DBManager.save_resume_version(
        user_id=user_id,
        resume_text=text_to_save,
        label=req.version_label,
        target_role=req.target_role or "General"
    )
    return {
        "message": "Resume version created successfully.",
        "id": version_id,
        "version_id": version_id,
        "version_label": req.version_label,
        "target_role": req.target_role
    }


@router.get("/versions/{version_id}/preview")
async def preview_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Previews a specific resume version with ownership verification.
    """
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume version not found or access denied."
        )

    sections = ResumeCleaner.segment_sections(version["resume_text"])
    skills_data = SkillExtractor.extract_skills(version["resume_text"], sections)
    return {
        "id": version["id"],
        "label": version["version_label"],
        "target_role": version.get("target_role") or "General",
        "created_at": version["created_at"],
        "resume_text": version["resume_text"],
        "sections": sections,
        "skills": [s["skill"] for s in skills_data]
    }


@router.post("/versions/{version_id}/compare")
@router.get("/versions/compare")
@router.post("/versions/compare")
async def compare_resume_versions(
    version_id: Optional[int] = None,
    with_version_id: Optional[int] = None,
    id1: Optional[int] = None,
    id2: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Compares two resume versions for diffs, shared skills, and unique skills.
    Enforces user ownership for both versions.
    """
    vid1 = version_id or id1
    vid2 = with_version_id or id2
    if not vid1 or not vid2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two version IDs must be provided for comparison."
        )

    v1 = DBManager.get_resume_version_by_id(vid1)
    v2 = DBManager.get_resume_version_by_id(vid2)

    if not v1 or v1["user_id"] != current_user["id"] or not v2 or v2["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both resume versions not found or access denied."
        )

    s1 = set(s["skill"] for s in SkillExtractor.extract_skills(v1["resume_text"]))
    s2 = set(s["skill"] for s in SkillExtractor.extract_skills(v2["resume_text"]))

    shared_skills = sorted(list(s1.intersection(s2)))
    unique_to_v1 = sorted(list(s1 - s2))
    unique_to_v2 = sorted(list(s2 - s1))

    import difflib
    lines1 = v1["resume_text"].splitlines()
    lines2 = v2["resume_text"].splitlines()
    diff = list(difflib.unified_diff(lines1, lines2, lineterm=""))

    res_data = {
        "version_1": {
            "id": v1["id"],
            "label": v1["version_label"],
            "target_role": v1.get("target_role"),
            "word_count": len(v1["resume_text"].split()),
            "skills_count": len(s1),
            "unique_skills": unique_to_v1
        },
        "version_2": {
            "id": v2["id"],
            "label": v2["version_label"],
            "target_role": v2.get("target_role"),
            "word_count": len(v2["resume_text"].split()),
            "skills_count": len(s2),
            "unique_skills": unique_to_v2
        },
        "version_a": {
            "id": v1["id"],
            "label": v1["version_label"],
            "target_role": v1.get("target_role"),
            "word_count": len(v1["resume_text"].split()),
            "skills_count": len(s1),
            "unique_skills": unique_to_v1
        },
        "version_b": {
            "id": v2["id"],
            "label": v2["version_label"],
            "target_role": v2.get("target_role"),
            "word_count": len(v2["resume_text"].split()),
            "skills_count": len(s2),
            "unique_skills": unique_to_v2
        },
        "diff_lines": diff,
        "shared_skills": shared_skills,
        "similarity_skills_ratio": round(len(shared_skills) / max(1, len(s1.union(s2))), 2)
    }
    return res_data


@router.delete("/versions/{version_id}")
async def delete_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Deletes a specific resume version with ownership checks.
    Preserves original uploaded files if it is the only version.
    """
    user_id = current_user["id"]
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume version not found or access denied."
        )

    all_versions = DBManager.get_resume_versions(user_id)
    if len(all_versions) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the sole resume version. Upload or create an alternative version first."
        )

    deleted = DBManager.delete_resume_version(version_id, user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume version not found or access denied."
        )

    return {"message": "Resume version deleted successfully.", "version_id": version_id}


@router.get("/versions/{version_id}/download")
async def download_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Generates plain-text export content for download.
    """
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume version not found or access denied."
        )

    return {
        "filename": f"Resume_{version['version_label'].replace(' ', '_')}.txt",
        "content": version["resume_text"],
        "target_role": version.get("target_role") or "General"
    }


@router.post("/versions/restore/{version_id}")
async def restore_resume_version(
    version_id: int,
    current_user: dict = Depends(get_current_user)
):
    version = DBManager.get_resume_version_by_id(version_id)
    if not version or version["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found."
        )
        
    cleaned_sections = ResumeCleaner.segment_sections(version["resume_text"])
    cleaned_full_text = "\n\n".join([f"[{sec.upper()}]\n{content}" for sec, content in cleaned_sections.items() if content])
    extracted_skills_data = SkillExtractor.extract_skills(cleaned_full_text, cleaned_sections)
    skills_list = [item["skill"] for item in extracted_skills_data]
    
    ProfileStore.store_profile(
        user_id=current_user["id"],
        resume_text=version["resume_text"],
        skills=skills_list
    )
    return {"message": "Version restored successfully.", "skills": skills_list}

# ATS Score endpoints
from pydantic import BaseModel as PydanticModel
from typing import Optional
from app.llm.ats_scorer import ATSScorer

class ATSScoreRequest(PydanticModel):
    job_description: str
    resume_text: Optional[str] = None

@router.post("/ats/score")
async def calculate_ats_score(
    request: ATSScoreRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Calculate ATS compatibility score for resume against job description
    """
    resume_text = request.resume_text
    if not resume_text:
        # Fetch user's latest resume
        db = SessionLocal()
        try:
            from app.db.models import ResumeVersion
            latest_resume = db.query(ResumeVersion).filter(
                ResumeVersion.user_id == current_user["id"]
            ).order_by(ResumeVersion.created_at.desc()).first()
            
            if not latest_resume:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No resume found for user. Please upload a resume first."
                )
            
            resume_text = latest_resume.resume_text
        finally:
            db.close()
    
    if not resume_text or len(resume_text) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume text is too short (minimum 50 characters)"
        )
    
    if not request.job_description or len(request.job_description) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description is too short (minimum 50 characters)"
        )
    
    try:
        ats_result = await ATSScorer.generate_ats_score_detailed(
            resume_text,
            request.job_description
        )
        return ats_result
    except Exception as e:
        logger.exception(f"Error calculating ATS score: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error calculating ATS score"
        )

@router.post("/ats/quick-check")
async def quick_ats_check(request: ATSScoreRequest):
    """Quick ATS compatibility check"""
    if not request.resume_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resume_text is required for quick check"
        )
    
    try:
        keyword_score, keywords = ATSScorer.calculate_keyword_match(
            request.resume_text,
            request.job_description
        )
        
        skills_score, skills = ATSScorer.calculate_skills_match(
            request.resume_text,
            request.job_description
        )
        
        format_score, issues = ATSScorer.check_ats_formatting(request.resume_text)
        
        return {
            "keyword_match_score": int(keyword_score),
            "skills_match_score": int(skills_score),
            "formatting_score": int(format_score),
            "average_score": int((keyword_score + skills_score + format_score) / 3),
            "formatting_issues": issues,
            "matched_skills": skills.get('soft_keywords', []) + skills.get('technical_keywords', [])
        }
    except Exception as e:
        logger.exception(f"Error performing ATS check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error performing ATS check"
        )

@router.get("/ats/formatting-tips")
async def get_ats_formatting_tips():
    """Get tips for ATS-friendly resume formatting"""
    return {
        "do": [
            "Use standard section headers: Summary, Experience, Education, Skills, Projects",
            "Use bullet points (•) for better readability",
            "Include quantifiable achievements (e.g., '30% improvement in performance')",
            "Match job description keywords where appropriate",
            "Use standard fonts (Arial, Calibri, Helvetica)",
            "Stick to standard formatting (no graphics, charts, or logos)",
            "Use standard dates format (MM/YYYY or Month Year)",
            "Include relevant keywords naturally throughout the resume"
        ],
        "dont": [
            "Avoid tables, columns, or complex layouts",
            "Don't use graphics, images, or special characters",
            "Don't use fancy fonts or unusual colors",
            "Avoid multiple font sizes or styles",
            "Don't use PDFs with embedded images (use plain text-based PDFs)",
            "Avoid URLs with tracking parameters or shortened links",
            "Don't use abbreviations unless they're industry standard",
            "Avoid irrelevant personal information"
        ],
        "technical_keywords": list(ATSScorer.TECHNICAL_SKILLS)[:20],
        "soft_skills": list(ATSScorer.SOFT_SKILLS),
        "required_sections": list(ATSScorer.REQUIRED_SECTIONS)
    }

