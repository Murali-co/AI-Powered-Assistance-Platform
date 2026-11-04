from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# --- Password Policy Constants (AI Powered Assistance Platform H6 Remediation) ---
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# --- Authentication ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="Password must be between 10 and 128 characters long"
    )
    full_name: str = Field(..., min_length=1)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH, description="Current account password")
    new_password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="New password must be between 10 and 128 characters"
    )

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    created_at: Optional[datetime] = None
    two_factor_enabled: Optional[bool] = False
    auto_approve_external_actions: Optional[bool] = False
    is_admin: Optional[bool] = False
    email_verified: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    requires_2fa: Optional[bool] = False
    pending_token: Optional[str] = None

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None

class TwoFactorConfirmRequest(BaseModel):
    code: str
    secret: Optional[str] = None
    password: Optional[str] = None

class TwoFactorDisableRequest(BaseModel):
    password: str

class TwoFactorVerifyRequest(BaseModel):
    pending_token: str
    code: str


# --- Resume / Profile ---
class SkillGapRequest(BaseModel):
    target_role: str

class LearningResource(BaseModel):
    title: str
    url: str

class SkillGapResponse(BaseModel):
    present_skills: List[str]
    missing_skills: List[str]
    skill_score: int
    recommendations: List[str]
    learning_resources: List[Union[LearningResource, str]]

class CoverLetterRequest(BaseModel):
    target_role: str
    company_name: Optional[str] = None
    tone: str = "formal"  # formal, casual, creative

class CoverLetterResponse(BaseModel):
    cover_letter: str


# --- Resume Tailoring ---
class ResumeTailorRequest(BaseModel):
    job_id: Optional[Union[str, int]] = None
    job_description: Optional[str] = None

class KeywordChange(BaseModel):
    original: str
    optimized: str

class ResumeTailorResponse(BaseModel):
    tailored_resume: str
    keyword_changes: List[KeywordChange]
    ats_score_estimate: int


# --- Jobs ---
class JobFilterCriteria(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    hours_old: Optional[int] = 48
    job_type: Optional[str] = None  # remote, hybrid, onsite, any

class JobOut(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = ""
    description: Optional[str] = ""
    url: Optional[str] = ""
    posted_at: Optional[str] = ""
    posted_ts: Optional[str] = ""
    source: Optional[str] = "custom"
    match_score: Optional[float] = None
    matched_skills: Optional[List[str]] = None
    missing_skills: Optional[List[str]] = None
    job_type: Optional[str] = None  # remote, hybrid, onsite
    bucket: Optional[str] = None

class JobListResponse(BaseModel):
    jobs: List[JobOut]


# --- Applications ---
class ApplicationPackageResponse(BaseModel):
    cover_letter: str
    resume_bullets: List[str]
    key_points: List[str]
    suggested_subject_line: str

class ApplicationSubmitRequest(BaseModel):
    job_id: str
    status: str = "applied"
    notes: Optional[str] = None
    cover_letter: Optional[str] = None
    resume_bullets: Optional[Union[List[str], str]] = None
    location: Optional[str] = None
    job_url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    resume_version_id: Optional[int] = None
    tone: Optional[str] = "formal"

class ApplicationHistoryOut(BaseModel):
    id: str
    user_id: int
    job_id: str
    job_title: str
    company: str
    applied_at: str
    status: str
    cover_letter: Optional[str] = ""
    resume_bullets: Optional[List[str]] = None
    notes: Optional[str] = ""
    location: Optional[str] = None
    job_url: Optional[str] = None
    resume_version_id: Optional[int] = None
    tone: Optional[str] = None
    status_history: Optional[List[Dict[str, Any]]] = None


# --- Email Verification & Password Reset ---
class ResendVerificationRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="Password must be between 10 and 128 characters"
    )

class VerificationResponse(BaseModel):
    message: str
    verified: bool

class PasswordResetResponse(BaseModel):
    message: str
    success: bool


# --- Job Applications ---
class JobApplicationCreate(BaseModel):
    job_id: str
    company: str
    title: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    cover_letter: Optional[str] = None
    notes: Optional[str] = None

class JobApplicationOut(BaseModel):
    id: int
    user_id: int
    job_id: str
    company: str
    title: str
    location: Optional[str] = None
    job_url: Optional[str] = None
    applied_date: datetime
    status: str
    cover_letter: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class JobApplicationListResponse(BaseModel):
    applications: List[JobApplicationOut]
    total: int
    skip: int
    limit: int

class WeeklySummaryOut(BaseModel):
    total_applications: int
    companies: List[str]
    applications: List[JobApplicationOut]
