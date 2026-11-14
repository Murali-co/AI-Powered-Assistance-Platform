import uuid
import json
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.vector_db.profile_store import ProfileStore
from app.jobs.matcher import JobMatcher
from app.llm.ollama_client import OllamaClient
from app.utils.limiter import limiter
from app.interview.adaptive_engine import AdaptiveInterviewEngine
from app.db.session import SessionLocal
from app.db.models import JobPosting, VerifiedProfile

router = APIRouter(prefix="/interview", tags=["interview"])


class StartRequest(BaseModel):
    job_id: Optional[str] = None
    target_role: Optional[str] = None
    interview_mode: Optional[str] = "mixed"  # technical, behavioral, project-based, mixed
    initial_difficulty: Optional[int] = 3


class AnswerRequest(BaseModel):
    session_id: str
    answer: str


class HintRequest(BaseModel):
    session_id: str


def format_chat_history(history: List[Dict[str, Any]]) -> str:
    lines = []
    for msg in history:
        role = "Interviewer" if msg.get("role") == "assistant" else "Candidate"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)


@router.post("/start")
@limiter.limit("5/minute")
async def start_interview(
    request: Request,
    req: StartRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["id"]
    profile = ProfileStore.get_profile(user_id) or {}
    resume_text = profile.get("resume_text", "")
    skills = profile.get("skills", [])

    if not resume_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume not uploaded. Please upload your resume before starting a mock interview."
        )

    # 1. Fetch verified profile if exists
    db = SessionLocal()
    verified_skills = list(skills)
    skill_gaps = []
    job_title = req.target_role or "Software Professional"
    job_desc = "General technical and problem-solving interview."
    try:
        vp = db.query(VerifiedProfile).filter(VerifiedProfile.user_id == user_id).first()
        if vp:
            try:
                v_skills = json.loads(vp.skills)
                if isinstance(v_skills, list) and v_skills:
                    verified_skills = v_skills
            except Exception:
                pass

        # 2. Fetch Job Description if job_id provided
        if req.job_id:
            db_job = db.query(JobPosting).filter(JobPosting.id == str(req.job_id)).first()
            if db_job:
                job_title = db_job.title
                job_desc = db_job.description
                try:
                    req_skills = json.loads(db_job.required_skills or "[]")
                    skill_gaps = [s for s in req_skills if s.lower() not in [vs.lower() for vs in verified_skills]]
                except Exception:
                    pass
            else:
                collection = JobMatcher.get_collection()
                job_data = collection.get(ids=[str(req.job_id)])
                if job_data and job_data["ids"]:
                    job_title = job_data["metadatas"][0].get("title", job_title)
                    job_desc = job_data["documents"][0]
    finally:
        db.close()

    initial_diff = max(1, min(5, req.initial_difficulty or 3))
    mode = req.interview_mode or "mixed"

    # Generate first question
    q_data = await AdaptiveInterviewEngine.generate_question(
        job_title=job_title,
        job_description=job_desc,
        verified_skills=verified_skills,
        skill_gaps=skill_gaps,
        interview_mode=mode,
        difficulty_level=initial_diff,
        topics_covered=[],
        is_first=True
    )

    first_question = q_data["question"]
    topic = q_data["topic"]
    q_type = q_data["question_type"]

    session_id = f"session_{uuid.uuid4().hex[:12]}"
    initial_history = [
        {
            "role": "assistant",
            "content": first_question,
            "topic": topic,
            "question_type": q_type,
            "difficulty_level": initial_diff,
            "turn_index": 1
        }
    ]

    DBManager.create_interview_session(
        session_id=session_id,
        user_id=user_id,
        job_id=req.job_id,
        target_role=job_title,
        chat_history=json.dumps(initial_history),
        interview_mode=mode,
        difficulty_level=initial_diff,
        topics_covered=json.dumps([topic]),
        metadata_json=json.dumps({
            "skill_gaps": skill_gaps,
            "verified_skills_count": len(verified_skills),
            "hints_used": 0
        })
    )

    return {
        "session_id": session_id,
        "question": first_question,
        "topic": topic,
        "question_type": q_type,
        "difficulty_level": initial_diff,
        "difficulty_label": AdaptiveInterviewEngine.DIFFICULTY_LABELS[initial_diff],
        "question_index": 1,
        "max_questions": 5
    }


@router.post("/answer")
@limiter.limit("10/minute")
async def submit_answer(
    request: Request,
    req: AnswerRequest,
    current_user: dict = Depends(get_current_user)
):
    session = DBManager.get_interview_session(req.session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )

    if session["is_finished"]:
        return {
            "session_id": req.session_id,
            "is_finished": True,
            "message": "Interview session is already concluded."
        }

    chat_history: List[Dict[str, Any]] = json.loads(session["chat_history"])
    current_diff = session.get("difficulty_level") or 3
    topics_covered: List[str] = json.loads(session.get("topics_covered") or "[]")
    mode = session.get("interview_mode") or "mixed"

    # Identify the question being answered (last assistant message)
    last_assistant_msg = next((m for m in reversed(chat_history) if m["role"] == "assistant"), None)
    curr_question = last_assistant_msg["content"] if last_assistant_msg else "General question"
    q_type = last_assistant_msg.get("question_type") or AdaptiveInterviewEngine.determine_question_type(curr_question, mode)

    # 1. Evaluate candidate answer using rubric
    eval_result = await AdaptiveInterviewEngine.evaluate_answer(
        question=curr_question,
        answer=req.answer,
        question_type=q_type,
        difficulty_level=current_diff
    )

    # Record user message with its structured evaluation
    chat_history.append({
        "role": "user",
        "content": req.answer,
        "evaluation": eval_result,
        "turn_index": len([m for m in chat_history if m["role"] == "assistant"])
    })

    # Collect past scores for adaptive difficulty calculation
    past_scores = [
        m["evaluation"]["score"] for m in chat_history
        if m["role"] == "user" and "evaluation" in m and "score" in m["evaluation"]
    ]
    latest_score = eval_result["score"]

    # 2. Deterministic Adaptive Transition
    new_difficulty, transition_reason = AdaptiveInterviewEngine.compute_adaptive_transition(
        current_difficulty=current_diff,
        latest_score=latest_score,
        recent_scores=past_scores[:-1]
    )

    question_count = sum(1 for m in chat_history if m["role"] == "assistant")

    # If completed 5 questions, finish interview session
    if question_count >= 5:
        overall_score = int(sum(past_scores) / len(past_scores)) if past_scores else latest_score
        DBManager.update_interview_session(
            session_id=req.session_id,
            chat_history=json.dumps(chat_history),
            is_finished=True,
            score=overall_score,
            difficulty_level=new_difficulty,
            topics_covered=json.dumps(topics_covered)
        )
        return {
            "session_id": req.session_id,
            "is_finished": True,
            "current_evaluation": eval_result,
            "overall_score": overall_score,
            "final_difficulty": new_difficulty,
            "final_difficulty_label": AdaptiveInterviewEngine.DIFFICULTY_LABELS[new_difficulty],
            "transition_reason": transition_reason
        }

    # 3. Generate Next Question with Adaptive Progression
    profile = ProfileStore.get_profile(current_user["id"]) or {}
    verified_skills = profile.get("skills", [])
    meta = json.loads(session.get("metadata_json") or "{}")
    skill_gaps = meta.get("skill_gaps", [])

    follow_up_reason = eval_result.get("follow_up_reason") if eval_result.get("follow_up_needed") else None

    next_q_data = await AdaptiveInterviewEngine.generate_question(
        job_title=session.get("target_role") or "Target Position",
        job_description="",
        verified_skills=verified_skills,
        skill_gaps=skill_gaps,
        interview_mode=mode,
        difficulty_level=new_difficulty,
        topics_covered=topics_covered,
        is_first=False,
        follow_up_reason=follow_up_reason
    )

    next_question = next_q_data["question"]
    next_topic = next_q_data["topic"]
    next_q_type = next_q_data["question_type"]

    if next_topic not in topics_covered:
        topics_covered.append(next_topic)

    chat_history.append({
        "role": "assistant",
        "content": next_question,
        "topic": next_topic,
        "question_type": next_q_type,
        "difficulty_level": new_difficulty,
        "turn_index": question_count + 1
    })

    DBManager.update_interview_session(
        session_id=req.session_id,
        chat_history=json.dumps(chat_history),
        is_finished=False,
        difficulty_level=new_difficulty,
        topics_covered=json.dumps(topics_covered)
    )

    return {
        "session_id": req.session_id,
        "is_finished": False,
        "current_evaluation": eval_result,
        "next_question": next_question,
        "next_topic": next_topic,
        "next_question_type": next_q_type,
        "difficulty_level": new_difficulty,
        "difficulty_label": AdaptiveInterviewEngine.DIFFICULTY_LABELS[new_difficulty],
        "transition_reason": transition_reason,
        "question_index": question_count + 1,
        "max_questions": 5
    }


@router.post("/hint")
@limiter.limit("10/minute")
async def request_hint(
    request: Request,
    req: HintRequest,
    current_user: dict = Depends(get_current_user)
):
    session = DBManager.get_interview_session(req.session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )

    chat_history = json.loads(session["chat_history"])
    last_assistant_msg = next((m for m in reversed(chat_history) if m["role"] == "assistant"), None)
    if not last_assistant_msg:
        raise HTTPException(status_code=400, detail="No active question to provide a hint for.")

    curr_question = last_assistant_msg["content"]
    q_type = last_assistant_msg.get("question_type", "technical")
    diff = session.get("difficulty_level") or 3

    hint = AdaptiveInterviewEngine.generate_hint(
        question=curr_question,
        question_type=q_type,
        difficulty_level=diff
    )

    # Record hint request in session metadata without reducing score
    meta = json.loads(session.get("metadata_json") or "{}")
    meta["hints_used"] = meta.get("hints_used", 0) + 1
    DBManager.update_interview_session(
        session_id=req.session_id,
        chat_history=session["chat_history"],
        is_finished=session["is_finished"],
        metadata_json=json.dumps(meta)
    )

    return {
        "session_id": req.session_id,
        "hint": hint,
        "hints_used": meta["hints_used"]
    }


@router.get("/session/{session_id}")
async def get_session_state(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves full interview session state for seamless refresh survival and resume capability.
    Enforces strict ownership authorization.
    """
    session = DBManager.get_interview_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )

    chat_history = json.loads(session["chat_history"])
    last_assistant = next((m for m in reversed(chat_history) if m["role"] == "assistant"), None)
    last_user = next((m for m in reversed(chat_history) if m["role"] == "user"), None)

    diff = session.get("difficulty_level") or 3
    q_index = sum(1 for m in chat_history if m["role"] == "assistant")

    return {
        "session_id": session_id,
        "is_finished": session["is_finished"],
        "target_role": session.get("target_role"),
        "interview_mode": session.get("interview_mode"),
        "difficulty_level": diff,
        "difficulty_label": AdaptiveInterviewEngine.DIFFICULTY_LABELS.get(diff, "Mid-Level Professional"),
        "topics_covered": json.loads(session.get("topics_covered") or "[]"),
        "current_question": last_assistant.get("content") if last_assistant else None,
        "question_type": last_assistant.get("question_type") if last_assistant else "technical",
        "question_index": q_index,
        "max_questions": 5,
        "last_evaluation": last_user.get("evaluation") if last_user else None,
        "overall_score": session.get("score"),
        "history": chat_history
    }


@router.get("/report")
@limiter.limit("5/minute")
async def get_report(
    request: Request,
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    if not session_id:
        interviews = DBManager.get_user_interviews(current_user["id"])
        if not interviews:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview session not found."
            )
        session_id = interviews[0]["id"]

    session = DBManager.get_interview_session(session_id)
    if not session or session["user_id"] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )

    chat_history = json.loads(session["chat_history"])
    user_turns = [m for m in chat_history if m.get("role") == "user" and "evaluation" in m]

    if not session["is_finished"] and len(user_turns) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Interview session is still active. Please complete more questions before generating report."
        )

    # Return cached report if already available
    if session.get("feedback") and session.get("score") is not None:
        try:
            return json.loads(session["feedback"])
        except Exception:
            pass

    # Compile structured comprehensive report from actual turn evaluations
    scores = [turn["evaluation"]["score"] for turn in user_turns if "score" in turn["evaluation"]]
    avg_score = int(sum(scores) / len(scores)) if scores else 70

    all_strengths = []
    all_areas = []
    all_recommendations = []
    star_evaluations = []

    for turn in user_turns:
        ev = turn["evaluation"]
        all_strengths.extend(ev.get("strengths", []))
        all_areas.extend(ev.get("areas_to_improve", []))
        if ev.get("practice_recommendation"):
            all_recommendations.append(ev["practice_recommendation"])
        if ev.get("star_elements"):
            star_evaluations.append(ev["star_elements"])

    report_payload = {
        "session_id": session_id,
        "target_role": session.get("target_role") or "Target Role",
        "score": session.get("score") or avg_score,
        "feedback": "Outstanding technical communication and structured answers." if (session.get("score") or avg_score) >= 80 else "Good progress. Focus on structuring technical details.",
        "final_difficulty_level": session.get("difficulty_level") or 3,
        "final_difficulty_label": AdaptiveInterviewEngine.DIFFICULTY_LABELS.get(session.get("difficulty_level") or 3),
        "strengths": list(dict.fromkeys(all_strengths))[:5] or ["Clear communication", "Technical articulation"],
        "weaknesses": list(dict.fromkeys(all_areas))[:5] or ["Add quantifiable metrics to outcomes"],
        "suggestions": list(dict.fromkeys(all_recommendations))[:4] or ["Include performance numbers."],
        "practice_recommendations": list(dict.fromkeys(all_recommendations))[:4] or [
            "Structure behavioral responses with explicit STAR stages",
            "Quantify technical performance improvements with benchmark numbers"
        ],
        "topics_covered": json.loads(session.get("topics_covered") or "[]"),
        "star_breakdown": {
            "situation_coverage_pct": int(100 * sum(1 for s in star_evaluations if s.get("situation")) / max(1, len(star_evaluations))),
            "task_coverage_pct": int(100 * sum(1 for s in star_evaluations if s.get("task")) / max(1, len(star_evaluations))),
            "action_coverage_pct": int(100 * sum(1 for s in star_evaluations if s.get("action")) / max(1, len(star_evaluations))),
            "result_coverage_pct": int(100 * sum(1 for s in star_evaluations if s.get("result")) / max(1, len(star_evaluations))),
        } if star_evaluations else None
    }

    DBManager.update_interview_session(
        session_id=session_id,
        chat_history=session["chat_history"],
        is_finished=True,
        feedback=json.dumps(report_payload),
        score=report_payload["score"]
    )

    return report_payload
