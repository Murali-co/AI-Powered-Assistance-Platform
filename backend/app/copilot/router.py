from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

from app.auth.utils import get_current_user
from app.rag.memory import ChatMemory
from app.rag.generator import RAGGenerator
from app.utils.limiter import limiter

router = APIRouter(prefix="/copilot", tags=["copilot"])

class CopilotChatRequest(BaseModel):
    message: str
    session_id: str
    job_id: Optional[str] = None
    stream: bool = False

def classify_query(message: str, job_id: Optional[str] = None) -> str:
    """
    Intelligently routes the query into one of three RAG modes based on keywords and parameters.
    """
    if job_id:
        return "job"
        
    msg_lower = message.lower()
    
    # Keyword taxonomy for routing
    job_keywords = [
        "job", "company", "requirement", "match", "align", "score", 
        "missing", "improve", "apply", "application", "proposal", 
        "interview", "hire", "recruiter", "position", "role"
    ]
    career_keywords = [
        "career", "roadmap", "become", "learn", "next", "course", 
        "study", "transition", "growth", "future", "certify", 
        "certification", "education", "skill up", "path", "trajectory"
    ]
    
    if any(kw in msg_lower for kw in career_keywords):
        return "career"
    if any(kw in msg_lower for kw in job_keywords):
        return "job"
        
    # Fallback to general resume / skill profile analysis
    return "resume"

@router.post("/chat")
@limiter.limit("10/minute")
async def copilot_chat_endpoint(
    request: Request,
    chat_request: CopilotChatRequest,
    current_user: dict = Depends(get_current_user)
):
    # 1. Automatically classify query to determine retrieval context type
    chat_type = classify_query(chat_request.message, chat_request.job_id)

    # 2. Fetch recent conversation history (last 10 messages)
    history = ChatMemory.get_messages(chat_request.session_id, current_user["id"], limit=10)

    # 3. Save user's query
    ChatMemory.add_message(
        session_id=chat_request.session_id,
        user_id=current_user["id"],
        role="user",
        content=chat_request.message
    )

    # 4. Handle Streaming Response
    if chat_request.stream:
        async def event_generator():
            full_response_list = []
            try:
                async for token in RAGGenerator.generate_stream(
                    user_id=current_user["id"],
                    message=chat_request.message,
                    chat_type=chat_type,
                    history=history,
                    job_id=chat_request.job_id
                ):
                    full_response_list.append(token)
                    yield f"data: {json.dumps({'token': token, 'classified_as': chat_type})}\n\n"
                
                # Stream finished, save aggregated assistant reply
                assistant_reply = "".join(full_response_list)
                if assistant_reply.strip():
                    ChatMemory.add_message(
                        session_id=chat_request.session_id,
                        user_id=current_user["id"],
                        role="assistant",
                        content=assistant_reply
                    )
            except Exception as e:
                logger.exception(f"Error during Copilot stream: {e}")
                yield f"data: {json.dumps({'error': 'Failed to generate response'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 5. Handle Standard JSON Response
    else:
        try:
            response_text = await RAGGenerator.generate_response(
                user_id=current_user["id"],
                message=chat_request.message,
                chat_type=chat_type,
                history=history,
                job_id=chat_request.job_id
            )
            
            # Save assistant response to SQLite database
            ChatMemory.add_message(
                session_id=chat_request.session_id,
                user_id=current_user["id"],
                role="assistant",
                content=response_text
            )
            
            return {
                "response": response_text,
                "classified_as": chat_type
            }
        except Exception as e:
            logger.exception(f"Failed to generate Copilot response: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate Copilot response"
            )

from starlette.concurrency import run_in_threadpool

@router.get("/sessions", response_model=List[str])
async def list_copilot_sessions(current_user: dict = Depends(get_current_user)):
    return await run_in_threadpool(ChatMemory.get_sessions, current_user["id"])

@router.get("/history/{session_id}", response_model=List[Dict[str, Any]])
async def get_copilot_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    return await run_in_threadpool(ChatMemory.get_messages, session_id, current_user["id"], limit=50)

@router.delete("/session/{session_id}")
async def delete_copilot_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    await run_in_threadpool(ChatMemory.clear_session, session_id, current_user["id"])
    return {"message": f"Session {session_id} deleted successfully."}
