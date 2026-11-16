from __future__ import annotations

from typing import Any, Dict, Literal
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.db.session import SessionLocal
from app.db.models import InterviewSession, JobPosting
from app.vector_db.profile_store import ProfileStore
from . import service

from .adaptive_engine import AdaptiveInterviewEngine

router = APIRouter(prefix="/interview", tags=["interview"])
engine = AdaptiveInterviewEngine()


class InterviewPromptRequest(BaseModel):
    question_index: int = 0


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=12000)
    question: str = Field(..., min_length=1, max_length=2000)


@router.get("/health")
async def interview_health() -> Dict[str, str]:
    return {"status": "ok", "service": "interview"}


@router.get("/next-question")
async def next_question(question_index: int = 0, current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    if question_index < 0:
        raise HTTPException(422, 'Question index must be non-negative.')
    question = engine.next_question(question_index)
    if question is None:
        return {"question": None, "completed": True}
    return {"question": question.prompt, "id": question.id, "completed": False}


@router.post("/score")
async def score_answer(payload: InterviewAnswerRequest, current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    return await service.evaluate(payload.question, payload.answer, 3)


class StartRequest(BaseModel):
    job_id: str | None = Field(default=None, max_length=200)
    target_role: str | None = Field(default=None, max_length=200)
    interview_mode: Literal['mixed', 'technical', 'behavioral', 'project-based'] = 'mixed'
    initial_difficulty: int = Field(default=3, ge=1, le=5)


class SessionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)


class AnswerRequest(SessionRequest):
    answer: str = Field(min_length=1, max_length=4000)
    question_index: int = Field(ge=1, le=5)
    request_id: uuid.UUID


def owned_session(session_id, user_id):
    session = DBManager.get_interview_session(session_id)
    if not session or session['user_id'] != user_id:
        raise HTTPException(404, 'Interview session not found.')
    return session


def update_if_current(session, **values):
    # Compare-and-swap prevents concurrent answers/hints from overwriting turns.
    with SessionLocal() as db:
        count = db.query(InterviewSession).filter(
            InterviewSession.id == session['id'],
            InterviewSession.user_id == session['user_id'],
            InterviewSession.chat_history == session['chat_history'],
            InterviewSession.is_finished.is_(False),
        ).update(values, synchronize_session=False)
        db.commit()
    if count != 1:
        raise HTTPException(409, 'Interview changed during this request. Reload the session before continuing.')


def job_context(job_id):
    with SessionLocal() as db:
        job = db.get(JobPosting, job_id)
        if not job:
            raise HTTPException(404, 'Job not found.')
        return {'title': job.title, 'description': (job.description or '')[:1500]}


def state_for(session):
    history = json.loads(session['chat_history'])
    questions = [turn for turn in history if turn['role'] == 'assistant']
    current = questions[-1]
    return {
        'session_id': session['id'], 'is_finished': session['is_finished'],
        'current_question': current['content'], 'question': current['content'],
        'question_type': current['question_type'], 'topic': current['topic'],
        'difficulty_level': session['difficulty_level'],
        'difficulty_label': service.LABELS[session['difficulty_level']],
        'question_index': len(questions), 'max_questions': 5,
        'topics_covered': json.loads(session.get('topics_covered') or '[]'),
        'target_role': session.get('target_role'),
    }


@router.post('/start')
async def start_interview(payload: StartRequest, user: dict = Depends(get_current_user)):
    profile = await run_in_threadpool(ProfileStore.get_profile, user['id'])
    if not profile or not profile.get('resume_text'):
        raise HTTPException(400, 'Upload and analyze your resume before starting an interview.')
    job = await run_in_threadpool(job_context, payload.job_id) if payload.job_id else None
    context = {'resume': profile['resume_text'][:3000], 'target_role': payload.target_role, 'job': job}
    question = await service.question_for(context, payload.interview_mode, payload.initial_difficulty, [])
    sid = str(uuid.uuid4())
    history = [{'role': 'assistant', 'content': question['question'], **{key: question[key] for key in ('topic', 'question_type')}}]
    await run_in_threadpool(DBManager.create_interview_session, session_id=sid, user_id=user['id'], job_id=payload.job_id,
                           target_role=payload.target_role or (job or {}).get('title') or 'General career interview',
                           chat_history=json.dumps(history), interview_mode=payload.interview_mode,
                           difficulty_level=payload.initial_difficulty, topics_covered=json.dumps([question['topic']]),
                           metadata_json=json.dumps({'context': context}))
    session = await run_in_threadpool(owned_session, sid, user['id'])
    return state_for(session)


@router.get('/session/{session_id}')
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    return state_for(await run_in_threadpool(owned_session, session_id, user['id']))


@router.post('/answer')
async def answer(payload: AnswerRequest, user: dict = Depends(get_current_user)):
    if not payload.answer.strip():
        raise HTTPException(422, 'Answer cannot be blank.')
    session = await run_in_threadpool(owned_session, payload.session_id, user['id'])
    meta = json.loads(session.get('metadata_json') or '{}')
    previous = meta.get('last_response')
    if meta.get('last_request_id') == str(payload.request_id) and previous:
        return previous
    state = state_for(session)
    if session['is_finished'] or payload.question_index != state['question_index']:
        raise HTTPException(409, 'This question has already been answered. Reload the session.')
    history = json.loads(session['chat_history'])
    evaluation = await service.evaluate(state['current_question'], payload.answer.strip(), session['difficulty_level'], question_type=state['question_type'])
    history.append({'role': 'user', 'content': payload.answer.strip(), 'evaluation': evaluation})
    difficulty = max(1, min(5, session['difficulty_level'] + (1 if evaluation['score'] >= 80 else -1 if evaluation['score'] < 50 else 0)))
    finished = state['question_index'] == 5
    topics = state['topics_covered']
    result = {'session_id': payload.session_id, 'is_finished': finished, 'current_evaluation': evaluation,
              'difficulty_level': difficulty, 'difficulty_label': service.LABELS[difficulty],
              'final_difficulty': difficulty, 'question_index': state['question_index'] + (not finished),
              'transition_reason': 'Difficulty adjusted using the evaluated answer.'}
    if not finished:
        question = await service.question_for(meta.get('context', {}), session['interview_mode'], difficulty, topics)
        history.append({'role': 'assistant', 'content': question['question'], 'topic': question['topic'], 'question_type': question['question_type']})
        topics = list(dict.fromkeys([*topics, question['topic']]))
        result.update(next_question=question['question'], next_topic=question['topic'], next_question_type=question['question_type'])
    meta.update(last_request_id=str(payload.request_id), last_response=result)
    scores = [turn['evaluation']['score'] for turn in history if turn['role'] == 'user']
    await run_in_threadpool(update_if_current, session, chat_history=json.dumps(history), is_finished=finished,
                           difficulty_level=difficulty, topics_covered=json.dumps(topics), metadata_json=json.dumps(meta),
                           score=round(sum(scores) / len(scores)) if finished else None)
    return result


@router.post('/hint')
async def hint(payload: SessionRequest, user: dict = Depends(get_current_user)):
    session = await run_in_threadpool(owned_session, payload.session_id, user['id'])
    if session['is_finished']:
        raise HTTPException(409, 'Interview is complete.')
    return {'session_id': payload.session_id, 'hint': 'Explain your approach, assumptions, trade-offs and supporting evidence. For behavioral questions, describe the situation, task, action and result.'}


@router.get('/report')
async def report(session_id: str, user: dict = Depends(get_current_user)):
    session = await run_in_threadpool(owned_session, session_id, user['id'])
    return service.report_for(session, json.loads(session['chat_history']))
