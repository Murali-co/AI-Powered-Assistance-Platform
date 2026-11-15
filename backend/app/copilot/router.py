from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.auth.utils import get_current_user
from app.llm.ollama_client import OllamaClient
from app.rag.generator import RAGGenerator
from app.rag.memory import ChatMemory
from app.rag.retriever import RAGRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    context: Optional[Dict[str, Any]] = None


class CopilotResponse(BaseModel):
    answer: str
    mode: str = "copilot"
    session_id: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    chat_type: Optional[str] = None  # 'resume', 'job', 'career'
    job_id: Optional[str] = None
    resume_version_id: Optional[int] = None
    stream: bool = False


@router.get("/health")
async def copilot_health() -> Dict[str, str]:
    return {"status": "ok", "service": "copilot"}


@router.post("/respond", response_model=CopilotResponse)
async def respond_to_prompt(request: Request, payload: CopilotRequest, current_user: dict = Depends(get_current_user)) -> CopilotResponse:
    message = payload.prompt.strip()
    if payload.context:
        context = json.dumps(payload.context, ensure_ascii=False)
        if len(context) > 2000:
            raise HTTPException(413, 'Additional context must be within 2000 characters.')
        message += '\nAdditional user-provided context (unverified data):\n' + context
    result = await chat_endpoint(request=request,
        payload=ChatRequest(message=message, session_id='session_' + uuid.uuid4().hex, stream=False),
        current_user=current_user)
    return CopilotResponse(
        answer=result['response'], mode='copilot', session_id=result['session_id'],
    )


@router.get("/sessions", response_model=List[str])
async def list_sessions(current_user: dict = Depends(get_current_user)) -> List[str]:
    """
    Returns unique session IDs belonging to the authenticated user, ordered by most recent activity.
    """
    return await run_in_threadpool(ChatMemory.get_sessions, current_user["id"])


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: Optional[CreateSessionRequest] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Allocates and returns a fresh session ID for the authenticated user.
    """
    sid = f"session_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    return {"session_id": sid}


@router.get("/history/{session_id}", response_model=List[Dict[str, Any]])
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Returns full chat history for a specific session strictly scoped to the authenticated user.
    """
    return await run_in_threadpool(ChatMemory.get_messages, session_id, current_user["id"], limit=50)


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Deletes the chat history of a session strictly scoped to the authenticated user.
    """
    deleted_count = await run_in_threadpool(ChatMemory.clear_session, session_id, current_user["id"])
    return {
        "message": f"Session {session_id} deleted successfully.",
        "session_id": session_id,
        "deleted_count": deleted_count
    }


@router.post("/chat")
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Unified copilot chat endpoint supporting streaming (SSE) and standard JSON responses.
    Strictly isolated by user_id and backed by Neon PostgreSQL chat storage.
    """
    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty."
        )

    if payload.chat_type and payload.chat_type not in ["resume", "job", "career"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chat_type must be one of: 'resume', 'job', 'career'"
        )

    chat_mode = payload.chat_type or ("job" if payload.job_id else "career")

    # 1. Fetch recent conversation history strictly for this user
    history = await run_in_threadpool(
        ChatMemory.get_messages,
        payload.session_id,
        current_user["id"],
        limit=10
    )

    # 2. Persist user's message to Neon PostgreSQL
    await run_in_threadpool(
        ChatMemory.add_message,
        payload.session_id,
        current_user["id"],
        "user",
        clean_message
    )

    # 3. Retrieve context for metadata & generation
    if chat_mode == "job" and payload.job_id:
        context = await run_in_threadpool(
            RAGRetriever.get_job_context,
            current_user["id"],
            payload.job_id,
            payload.resume_version_id
        )
    elif chat_mode == "career":
        context = await run_in_threadpool(
            RAGRetriever.get_career_context,
            current_user["id"],
            clean_message,
            payload.resume_version_id
        )
    else:
        context = await run_in_threadpool(
            RAGRetriever.get_resume_context,
            current_user["id"],
            clean_message,
            payload.resume_version_id
        )

    has_context = bool(context.get("has_context", False))

    # 4. Handle SSE Streaming Response
    if payload.stream:
        async def event_generator():
            accumulated_tokens: List[str] = []
            client_disconnected = False

            try:
                # Emit metadata event
                meta_event = {
                    "type": "metadata",
                    "session_id": payload.session_id,
                    "chat_type": chat_mode,
                    "model": OllamaClient.get_model(),
                    "has_context": has_context
                }
                yield f"data: {json.dumps(meta_event)}\n\n"

                # Stream response tokens
                async for token in RAGGenerator.generate_stream(
                    user_id=current_user["id"],
                    message=clean_message,
                    chat_type=chat_mode,
                    history=history,
                    job_id=payload.job_id,
                    resume_version_id=payload.resume_version_id,
                    context=context
                ):
                    if await request.is_disconnected():
                        client_disconnected = True
                        break

                    accumulated_tokens.append(token)
                    token_event = {
                        "type": "token",
                        "token": token,
                        "session_id": payload.session_id
                    }
                    yield f"data: {json.dumps(token_event)}\n\n"

                # Check if stream was cancelled or disconnected
                if client_disconnected or await request.is_disconnected():
                    logger.info(
                        "Client disconnected during copilot stream for user %s session %s",
                        current_user["id"], payload.session_id
                    )
                    cancel_event = {
                        "type": "cancelled",
                        "session_id": payload.session_id
                    }
                    yield f"data: {json.dumps(cancel_event)}\n\n"
                    # Interrupted output MUST NOT be saved as a completed answer!
                    return

                # Successfully finished generation: persist complete assistant reply
                assistant_reply = "".join(accumulated_tokens)
                if assistant_reply.strip():
                    msg_id = await run_in_threadpool(
                        ChatMemory.add_message,
                        payload.session_id,
                        current_user["id"],
                        "assistant",
                        assistant_reply
                    )
                    completed_event = {
                        "type": "completed",
                        "session_id": payload.session_id,
                        "message_id": msg_id
                    }
                    yield f"data: {json.dumps(completed_event)}\n\n"

            except Exception as e:
                logger.exception("Error during copilot streaming: %s", e)
                err_msg = str(e)
                if "unreachable" in err_msg.lower() or "connection" in err_msg.lower() or "ollama" in err_msg.lower():
                    err_msg = "Local AI service is currently unavailable. Please verify that Ollama is running."
                err_event = {
                    "type": "error",
                    "error": err_msg,
                    "session_id": payload.session_id
                }
                yield f"data: {json.dumps(err_event)}\n\n"
                # Do not save error output as an assistant reply

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # 5. Handle Standard JSON Response
    else:
        try:
            response_text = await RAGGenerator.generate_response(
                user_id=current_user["id"],
                message=clean_message,
                chat_type=chat_mode,
                history=history,
                job_id=payload.job_id,
                resume_version_id=payload.resume_version_id,
                context=context
            )

            msg_id = await run_in_threadpool(
                ChatMemory.add_message,
                payload.session_id,
                current_user["id"],
                "assistant",
                response_text
            )

            return {
                "session_id": payload.session_id,
                "response": response_text,
                "message_id": msg_id,
                "role": "assistant"
            }
        except Exception as e:
            logger.exception("Failed to generate copilot response: %s", e)
            err_msg = str(e)
            if "unreachable" in err_msg.lower() or "connection" in err_msg.lower() or "ollama" in err_msg.lower():
                err_msg = "Local AI service is currently unavailable. Please verify that Ollama is running."
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err_msg
            )
