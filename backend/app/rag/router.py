from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

from app.auth.utils import get_current_user
from app.rag.memory import ChatMemory
from app.rag.generator import RAGGenerator

router = APIRouter(prefix="/rag", tags=["rag"])

class ChatRequest(BaseModel):
    message: str
    chat_type: str  # 'resume', 'job', 'career'
    session_id: str
    job_id: Optional[str] = None
    stream: bool = False

@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    if request.chat_type not in ["resume", "job", "career"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chat_type must be one of: 'resume', 'job', 'career'"
        )

    # 1. Fetch recent conversation history from SQLite (e.g. last 10 messages)
    history = ChatMemory.get_messages(request.session_id, current_user["id"], limit=10)

    # 2. Save user's new message to SQLite memory database
    ChatMemory.add_message(
        session_id=request.session_id,
        user_id=current_user["id"],
        role="user",
        content=request.message
    )

    # 3. Handle Streaming Response
    if request.stream:
        async def event_generator():
            full_response_list = []
            try:
                async for token in RAGGenerator.generate_stream(
                    user_id=current_user["id"],
                    message=request.message,
                    chat_type=request.chat_type,
                    history=history,
                    job_id=request.job_id
                ):
                    full_response_list.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
                
                # Stream finished, save aggregated assistant reply
                assistant_reply = "".join(full_response_list)
                if assistant_reply.strip():
                    ChatMemory.add_message(
                        session_id=request.session_id,
                        user_id=current_user["id"],
                        role="assistant",
                        content=assistant_reply
                    )
            except Exception as e:
                logger.exception(f"Error during RAG stream: {e}")
                yield f"data: {json.dumps({'error': 'Failed to generate response'})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 4. Handle Standard JSON Response
    else:
        try:
            response_text = await RAGGenerator.generate_response(
                user_id=current_user["id"],
                message=request.message,
                chat_type=request.chat_type,
                history=history,
                job_id=request.job_id
            )
            
            # Save assistant response to SQLite database
            ChatMemory.add_message(
                session_id=request.session_id,
                user_id=current_user["id"],
                role="assistant",
                content=response_text
            )
            
            return {"response": response_text}
        except Exception as e:
            logger.exception(f"Failed to generate RAG response: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate RAG response"
            )

from starlette.concurrency import run_in_threadpool

@router.get("/sessions", response_model=List[str])
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """
    Lists unique session IDs for the current user.
    """
    return await run_in_threadpool(ChatMemory.get_sessions, current_user["id"])

@router.get("/history/{session_id}", response_model=List[Dict[str, Any]])
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns full chat history list of a specific session.
    """
    # Fetch messages
    return await run_in_threadpool(ChatMemory.get_messages, session_id, current_user["id"], limit=50)

@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Clears the chat history of a session.
    """
    await run_in_threadpool(ChatMemory.clear_session, session_id, current_user["id"])
    return {"message": f"Session {session_id} deleted successfully."}
