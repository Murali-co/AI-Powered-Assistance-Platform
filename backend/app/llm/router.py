import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from app.auth.utils import get_current_user
from app.auth.models import DBManager
from app.llm.multi_model import MultiModelManager
from app.db.session import SessionLocal
from app.db.models import User
from app.config import settings
from app.utils.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

class ModelSelectionRequest(BaseModel):
    model_name: str

    class Config:
        extra = "ignore"

class ModelInfo(BaseModel):
    name: str
    description: Optional[str] = None
    speed: Optional[str] = None
    quality: Optional[str] = None

@router.get("/available-models")
async def get_available_models(current_user: dict = Depends(get_current_user)):
    """
    Get list of available models from Ollama (M10/M12 protected)
    """
    models = await MultiModelManager.get_available_models()
    return {
        "models": models,
        "default_model": settings.OLLAMA_MODEL,
    }

@router.get("/recommended-models")
async def get_recommended_models(current_user: dict = Depends(get_current_user)):
    """
    Get list of recommended models organized by use case
    """
    recommended = MultiModelManager.get_recommended_models()
    return {
        "categories": recommended,
        "note": "These models can be pulled from Ollama: ollama pull <model_name>"
    }

@router.get("/model-info/{model_name}")
async def get_model_info(model_name: str, current_user: dict = Depends(get_current_user)):
    """
    Get detailed info about a specific model (M10/M12 protected)
    """
    info = await MultiModelManager.get_model_info(model_name)
    if info:
        return info
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_name}' not found. Make sure it's installed: ollama pull {model_name}"
        )

@router.get("/user-model-preference")
async def get_user_model_preference(current_user: dict = Depends(get_current_user)):
    """
    Get the user's selected LLM model
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == current_user["id"]).first()
        model_name = getattr(user, 'preferred_model', None) or settings.OLLAMA_MODEL
        return {
            "user_id": current_user["id"],
            "preferred_model": model_name,
            "default_model": settings.OLLAMA_MODEL
        }
    finally:
        db.close()

@router.post("/user-model-preference")
@router.post("/select")
@limiter.limit("20/minute")
async def set_user_model_preference(
    request: Request,
    body: ModelSelectionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Set the user's preferred LLM model for all LLM tasks
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == current_user["id"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Strictly enforce canonical model restriction
        if not MultiModelManager.is_approved_model(body.model_name):
            raise HTTPException(
                status_code=400,
                detail=f"Model '{body.model_name}' is not permitted. Platform is restricted to canonical model '{settings.OLLAMA_MODEL}'."
            )
        
        user.preferred_model = body.model_name
        db.commit()
        
        return {
            "message": "Model preference updated",
            "new_model": body.model_name,
            "note": "Changes will apply to the next LLM request"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to update model preference: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update model preference.")
    finally:
        db.close()

@router.get("/pull-model/{model_name}")
async def pull_model_instructions(model_name: str):
    """
    Get instructions for pulling the canonical model from Ollama
    """
    if not MultiModelManager.is_approved_model(model_name):
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model_name}' is not approved. Only '{settings.OLLAMA_MODEL}' is permitted."
        )
    return {
        "command": f"ollama pull {model_name}",
        "description": f"Pull and install the approved {model_name} model",
        "instructions": [
            "Make sure Ollama is running: ollama serve",
            f"In another terminal, run: ollama pull {model_name}",
            "Wait for the model to download and extract",
            "Verify installation via AI Engine Status"
        ]
    }
