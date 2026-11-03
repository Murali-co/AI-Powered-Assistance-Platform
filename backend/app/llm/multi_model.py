"""
Local Model Management for AI-Powered Assistance Platform
Enforces strict execution of approved local Ollama model (qwen3:14b only).
External LLM calls and alternative models are strictly prohibited.
"""

import logging
from typing import Dict, Any, List, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class MultiModelManager:
    """Manages local Ollama model verification and enforces qwen3:14b restriction"""

    @classmethod
    def get_canonical_model(cls) -> str:
        """Return the canonical approved model name."""
        return settings.OLLAMA_MODEL

    @classmethod
    def is_approved_model(cls, model_name: Optional[str]) -> bool:
        """
        Verify if a given model identifier matches the canonical approved model.
        Strictly permits only qwen3:14b (including valid tag prefixes/suffixes).
        """
        if not model_name:
            return False
        approved = settings.OLLAMA_MODEL.lower().strip()
        requested = model_name.lower().strip()
        return (
            requested == approved
            or requested.startswith(f"{approved}:")
            or approved.startswith(f"{requested}:")
        )

    @classmethod
    async def get_available_models(cls) -> List[Dict[str, Any]]:
        """
        Fetch available models from local Ollama and filter strictly to the approved model (qwen3:14b).
        Does not fabricate models when Ollama is down and filters out any non-approved models.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    # Filter strictly to the approved model
                    approved_models = [
                        {
                            "name": m.get("name") or m.get("model"),
                            "digest": m.get("digest"),
                            "size": m.get("size"),
                            "modified_at": m.get("modified_at"),
                            "status": "approved",
                        }
                        for m in models
                        if m and cls.is_approved_model(m.get("name") or m.get("model"))
                    ]
                    return approved_models
        except Exception as e:
            logger.warning(f"Unable to fetch models from Ollama ({settings.OLLAMA_BASE_URL}): {e}")

        # When Ollama is unreachable or model not found, return empty list truthfully
        return []

    @classmethod
    async def get_model_info(cls, model_name: str) -> Optional[Dict[str, Any]]:
        """Get details about the approved model from local Ollama"""
        if not cls.is_approved_model(model_name):
            logger.warning(f"Rejected model info query for unauthorized model: {model_name}")
            return None

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/show",
                    json={"name": model_name}
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.warning(f"Error fetching model info for '{model_name}': {e}")

        return None

    @classmethod
    def get_default_model(cls) -> str:
        """Get the canonical approved model from config"""
        return settings.OLLAMA_MODEL

    @classmethod
    def get_recommended_models(cls) -> Dict[str, List[Dict[str, str]]]:
        """
        Get list of recommended models.
        Strictly returns only the approved qwen3:14b model across all operational categories.
        """
        canonical = settings.OLLAMA_MODEL
        single_approved_entry = [
            {
                "name": canonical,
                "description": "Privacy-Preserving Local Qwen3 14B (Canonical Approved Engine)",
                "speed": "optimal",
                "quality": "high",
                "status": "canonical"
            }
        ]
        return {
            "general": single_approved_entry,
            "conversation": single_approved_entry,
            "creative": single_approved_entry,
            "fast": single_approved_entry,
        }

