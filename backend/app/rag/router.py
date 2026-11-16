from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter
from app.copilot.router import (
    chat_endpoint,
    list_sessions,
    create_session,
    get_session_history,
    delete_session,
    ChatRequest,
    CreateSessionRequest,
)

router = APIRouter(prefix="/rag", tags=["rag"])

# Reconciled compatibility routes matching /copilot contracts
router.add_api_route(
    "/chat",
    chat_endpoint,
    methods=["POST"],
    summary="Compatible RAG / Copilot Chat Endpoint"
)

router.add_api_route(
    "/sessions",
    list_sessions,
    methods=["GET"],
    response_model=List[str],
    summary="List RAG / Copilot Sessions"
)

router.add_api_route(
    "/sessions",
    create_session,
    methods=["POST"],
    status_code=201,
    response_model=Dict[str, str],
    summary="Create RAG / Copilot Session"
)

router.add_api_route(
    "/history/{session_id}",
    get_session_history,
    methods=["GET"],
    response_model=List[Dict[str, Any]],
    summary="Get RAG / Copilot Session History"
)

router.add_api_route(
    "/session/{session_id}",
    delete_session,
    methods=["DELETE"],
    response_model=Dict[str, Any],
    summary="Delete RAG / Copilot Session"
)
