import os
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

# Lazy-loaded model to keep startup fast and to avoid duplicate concurrent initialization.
_model = None
_model_device: Optional[str] = None
_load_error: Optional[str] = None
_model_lock = threading.RLock()


def _select_model_device() -> str:
    """Return 'cpu' for stable local loading to avoid CUDA/meta-tensor failures and preserve VRAM for Ollama."""
    device_override = os.getenv("AI_POWERED_ASSISTANCE_PLATFORM_EMBED_DEVICE")
    if device_override:
        return device_override
    return "cpu"


def _load_model_for_device(device: str):
    from sentence_transformers import SentenceTransformer

    logger.info("Initializing SentenceTransformer %s on device=%s", MODEL_NAME, device)
    model = SentenceTransformer(MODEL_NAME, device=device)
    return model


def get_embedding_model():
    global _model, _model_device, _load_error

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        preferred_device = _select_model_device()
        candidates = [preferred_device]
        if preferred_device != "cpu":
            candidates.append("cpu")

        last_exc: Optional[Exception] = None
        for device in candidates:
            try:
                from sentence_transformers import SentenceTransformer  # local import for safer diagnostics

                _model = SentenceTransformer(MODEL_NAME, device=device)
                _model_device = device
                _load_error = None
                logger.info("SentenceTransformer %s initialized successfully on device=%s", MODEL_NAME, device)
                return _model
            except ImportError:
                _model = None
                _model_device = None
                _load_error = "sentence-transformers is not installed"
                logger.warning("sentence-transformers is not installed.")
                return None
            except Exception as exc:  # pragma: no cover - runtime/device-dependent path
                last_exc = exc
                _model = None
                _model_device = None
                logger.exception(
                    "SentenceTransformer %s failed to initialize on device=%s. This can occur when the model is loaded with an incompatible default device or stale cache state.",
                    MODEL_NAME,
                    device,
                )

        _load_error = (
            f"Failed to load SentenceTransformer model {MODEL_NAME} on selected device(s) "
            f"{candidates}: {type(last_exc).__name__}: {last_exc}"
            if last_exc is not None else f"Failed to load SentenceTransformer model {MODEL_NAME}"
        )
        logger.error(_load_error)
        return None


def check_embedding_status() -> Dict[str, Any]:
    """Check if the sentence-transformers embedding model is available."""
    try:
        model = get_embedding_model()
        if model is not None:
            return {
                "healthy": True,
                "model_name": MODEL_NAME,
                "device": _model_device,
                "error": None,
            }
        return {
            "healthy": False,
            "model_name": MODEL_NAME,
            "device": _model_device,
            "error": _load_error or "SentenceTransformer model unavailable",
        }
    except Exception as e:
        return {
            "healthy": False,
            "model_name": MODEL_NAME,
            "device": _model_device,
            "error": str(e),
        }


def embed_text(text: str) -> List[float]:
    model = get_embedding_model()
    if model is None:
        raise RuntimeError(
            f"Embedding model unavailable ({_load_error or f'{MODEL_NAME} could not be loaded'}). "
            "Semantic matching and vector search cannot produce valid embeddings without this dependency."
        )
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_embedding_model()
    if model is None:
        raise RuntimeError(
            f"Embedding model unavailable ({_load_error or f'{MODEL_NAME} could not be loaded'}). "
            "Semantic matching and vector search cannot produce valid embeddings without this dependency."
        )
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()


# Maintain un-monkeypatched references for testing core embedder behavior
_original_embed_text = embed_text
_original_embed_batch = embed_batch
