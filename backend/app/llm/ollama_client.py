import httpx
import asyncio
import json
import re
import time
import logging
from typing import AsyncGenerator, Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


def _clean_content(text: str) -> str:
    if not text:
        return ""
    # Strip any <think>...</think> reasoning traces if output in text
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    return cleaned if cleaned else text


class OllamaClient:
    TIMEOUT = getattr(settings, "OLLAMA_TIMEOUT", 120.0)
    MAX_RETRIES = 3

    @classmethod
    def get_base_url(cls) -> str:
        return settings.OLLAMA_BASE_URL

    @classmethod
    def get_model(cls) -> str:
        return settings.OLLAMA_MODEL

    @classmethod
    def get_num_ctx(cls) -> int:
        return getattr(settings, "OLLAMA_NUM_CTX", 4096)

    @classmethod
    def check_context_budget(cls, prompt: str, system: Optional[str] = None) -> int:
        """Estimate tokens and warn if context budget is approached or exceeded (M8)."""
        num_ctx = cls.get_num_ctx()
        total_len = len(prompt or "") + len(system or "")
        est_tokens = total_len // 4
        if est_tokens > int(num_ctx * 0.9):
            logger.warning(
                "Prompt size (~%d tokens) approaches or exceeds Ollama context budget (%d). Truncation or quality degradation may occur.",
                est_tokens, num_ctx
            )
        return est_tokens

    @classmethod
    async def check_service_status(cls, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Check whether Ollama is reachable and whether the target model is installed.
        Returns explicit diagnostics without crashing or masking failures.
        """
        target_model = model_name or cls.get_model()
        base_url = cls.get_base_url().rstrip('/')
        url = f"{base_url}/api/tags"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    models_data = res.json().get("models", [])
                    available_names = [
                        m.get("name") or m.get("model") for m in models_data if m
                    ]
                    # Check exact match or tag match
                    is_available = any(
                        target_model == m or m.startswith(f"{target_model}:") or target_model.startswith(f"{m}:")
                        for m in available_names
                    )
                    if is_available:
                        return {
                            "reachable": True,
                            "model_available": True,
                            "configured_model": target_model,
                            "available_models": available_names,
                            "status": "healthy",
                            "message": f"Ollama is reachable and '{target_model}' is ready.",
                            "install_command": None,
                        }
                    else:
                        msg = f"Model '{target_model}' is not installed in Ollama. Pull it with: ollama pull {target_model}"
                        return {
                            "reachable": True,
                            "model_available": False,
                            "configured_model": target_model,
                            "available_models": available_names,
                            "status": "missing_model",
                            "message": msg,
                            "error": msg,
                            "install_command": f"ollama pull {target_model}",
                        }
                msg = f"Ollama responded with status code {res.status_code}."
                return {
                    "reachable": True,
                    "model_available": False,
                    "configured_model": target_model,
                    "available_models": [],
                    "status": "degraded",
                    "message": msg,
                    "error": msg,
                    "install_command": None,
                }
        except httpx.ConnectError:
            msg = f"Ollama is not running at {base_url}. Start it with: ollama serve"
            return {
                "reachable": False,
                "model_available": False,
                "configured_model": target_model,
                "available_models": [],
                "status": "unreachable",
                "message": msg,
                "error": msg,
                "install_command": f"ollama pull {target_model}",
            }
        except httpx.TimeoutException:
            msg = f"Connection to Ollama at {base_url} timed out."
            return {
                "reachable": False,
                "model_available": False,
                "configured_model": target_model,
                "available_models": [],
                "status": "timeout",
                "message": msg,
                "error": msg,
                "install_command": None,
            }
        except Exception as e:
            msg = f"Ollama connection error: {type(e).__name__}: {str(e)}"
            return {
                "reachable": False,
                "model_available": False,
                "configured_model": target_model,
                "available_models": [],
                "status": "error",
                "message": msg,
                "error": msg,
                "install_command": None,
            }

    @classmethod
    async def check_model_available(cls, model_name: Optional[str] = None) -> bool:
        """
        Verify that the configured or requested model is available in local Ollama.
        """
        status = await cls.check_service_status(model_name)
        return status.get("model_available", False)

    @classmethod
    async def _request_with_retry(
        cls, 
        method: str, 
        path: str, 
        payload: Dict[str, Any], 
        retries: Optional[int] = None,
        deadline: Optional[float] = None
    ) -> httpx.Response:
        """
        Execute request with a single retry strategy bounded by an overall deadline (R2/M8).
        Timeouts are NEVER retried. Transient network errors are retried at most once.
        """
        overall_timeout = cls.TIMEOUT
        if deadline is None:
            deadline = time.monotonic() + overall_timeout

        max_attempts = retries if retries is not None else 2
        url = f"{cls.get_base_url().rstrip('/')}{path}"
        backoff = 1.0

        for attempt in range(max_attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"Ollama request exceeded overall deadline of {overall_timeout:.1f}s.")

            attempt_timeout = min(overall_timeout, remaining)

            try:
                async with httpx.AsyncClient(timeout=attempt_timeout) as client:
                    if method.upper() == "POST":
                        response = await client.post(url, json=payload)
                    else:
                        response = await client.get(url)
                    response.raise_for_status()
                    return response

            except httpx.TimeoutException as e:
                # R2/M8: DO NOT RETRY TIMEOUTS! Immediately raise clear deadline/timeout error.
                raise RuntimeError(
                    f"Ollama request timed out after {attempt_timeout:.1f}s (overall deadline exceeded)."
                ) from e

            except httpx.HTTPStatusError as e:
                detail = ""
                if e.response is not None:
                    try:
                        detail = e.response.text
                    except Exception:
                        detail = ""

                # 400/404 indicating bad request or model missing must NEVER be retried
                if e.response is not None and e.response.status_code in {400, 404}:
                    msg = detail or str(e)
                    raise RuntimeError(
                        f"Ollama rejected the request for model '{cls.get_model()}': {msg}. "
                        f"Ensure the model is available: ollama pull {cls.get_model()}"
                    ) from e

                # 5xx server errors
                remaining_after = deadline - time.monotonic()
                if attempt < max_attempts - 1 and remaining_after > (backoff + 1.0):
                    logger.warning("Ollama server error (HTTP %s). Retrying in %ss...", e.response.status_code, backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise RuntimeError(f"Ollama API request failed with status {e.response.status_code}: {detail or e}") from e

            except (httpx.ConnectError, httpx.NetworkError) as e:
                remaining_after = deadline - time.monotonic()
                if attempt < max_attempts - 1 and remaining_after > (backoff + 1.0):
                    logger.warning("Ollama connection attempt %d failed (network). Retrying in %ss...", attempt + 1, backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise RuntimeError(f"Ollama service unreachable at {cls.get_base_url()}: {e}") from e

            except httpx.HTTPError as e:
                remaining_after = deadline - time.monotonic()
                if attempt < max_attempts - 1 and remaining_after > (backoff + 1.0):
                    logger.warning("Ollama connection attempt %d failed (http). Retrying in %ss...", attempt + 1, backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise RuntimeError(f"Ollama HTTP error after {attempt + 1} attempts: {e}") from e

        raise RuntimeError("Ollama API request failed after retries.")

    @classmethod
    async def generate(
        cls, 
        prompt: str, 
        system: Optional[str] = None, 
        format: Optional[str] = None,
        think: Optional[bool] = False,
        timeout: Optional[float] = None
    ) -> str:
        cls.check_context_budget(prompt, system)

        overall_timeout = timeout if timeout is not None else cls.TIMEOUT
        deadline = time.monotonic() + overall_timeout

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": cls.get_model(),
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": cls.get_num_ctx(),
                "temperature": 0.3
            }
        }
        if format:
            payload["format"] = format  # e.g., "json"
        if think is not None:
            payload["think"] = think

        try:
            # Single unified execution with shared overall deadline
            response = await cls._request_with_retry("POST", "/api/chat", payload, retries=2, deadline=deadline)
            response_data = response.json()
            raw_text = response_data.get("message", {}).get("content", "") or response_data.get("response", "")
            return _clean_content(raw_text)
        except RuntimeError as e:
            err_msg = str(e).lower()
            # If request timed out, deadline was exceeded, model is missing, or service unreachable: DO NOT RETRY OR FALLBACK!
            if "timed out" in err_msg or "deadline" in err_msg or "pull" in err_msg or "unreachable" in err_msg:
                raise

            # Only fallback for parameter or endpoint rejection if deadline permits
            remaining = deadline - time.monotonic()
            if remaining <= 2.0:
                raise

            # Fallback for think parameter if rejected with 400
            if "think" in payload and "rejected the request" in err_msg:
                payload_fallback = dict(payload)
                del payload_fallback["think"]
                try:
                    response = await cls._request_with_retry("POST", "/api/chat", payload_fallback, retries=1, deadline=deadline)
                    response_data = response.json()
                    raw_text = response_data.get("message", {}).get("content", "") or response_data.get("response", "")
                    return _clean_content(raw_text)
                except RuntimeError as fb_err:
                    fb_msg = str(fb_err).lower()
                    if "timed out" in fb_msg or "deadline" in fb_msg or "pull" in fb_msg or "unreachable" in fb_msg:
                        raise

            # Fallback to /api/generate if /api/chat endpoint not found (404)
            remaining = deadline - time.monotonic()
            if remaining <= 2.0:
                raise

            gen_payload: Dict[str, Any] = {
                "model": cls.get_model(),
                "prompt": prompt,
                "stream": False,
                "options": payload["options"]
            }
            if system:
                gen_payload["system"] = system
            if format:
                gen_payload["format"] = format
            response = await cls._request_with_retry("POST", "/api/generate", gen_payload, retries=1, deadline=deadline)
            response_data = response.json()
            return _clean_content(response_data.get("response", ""))

    @classmethod
    async def generate_stream(
        cls, 
        prompt: str, 
        system: Optional[str] = None, 
        format: Optional[str] = None,
        think: Optional[bool] = False,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        cls.check_context_budget(prompt, system)

        overall_timeout = timeout if timeout is not None else cls.TIMEOUT
        deadline = time.monotonic() + overall_timeout

        url = f"{cls.get_base_url().rstrip('/')}/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": cls.get_model(),
            "messages": messages,
            "stream": True,
            "options": {
                "num_ctx": cls.get_num_ctx(),
                "temperature": 0.3
            }
        }
        if format:
            payload["format"] = format
        if think is not None:
            payload["think"] = think

        backoff = 1.0
        max_attempts = 2
        tokens_yielded = False

        for attempt in range(max_attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"Ollama streaming exceeded overall deadline of {overall_timeout:.1f}s.")

            attempt_timeout = min(overall_timeout, remaining)

            try:
                async with httpx.AsyncClient(timeout=attempt_timeout) as client:
                    async with client.stream("POST", url, json=payload) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("message", {}).get("content", "") or chunk.get("response", "")
                                if token:
                                    tokens_yielded = True
                                    yield token
                            except json.JSONDecodeError:
                                continue
                return
            except httpx.TimeoutException as e:
                # DO NOT RETRY TIMEOUTS!
                raise RuntimeError(
                    f"Ollama streaming timed out after {attempt_timeout:.1f}s (overall deadline exceeded)."
                ) from e
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code in {400, 404}:
                    raise RuntimeError(
                        f"Ollama rejected the streaming request for model '{cls.get_model()}': {e}. "
                        f"Make sure the model is available and pulled with 'ollama pull {cls.get_model()}'."
                    ) from e
                if tokens_yielded or attempt == max_attempts - 1 or (deadline - time.monotonic()) <= (backoff + 1.0):
                    raise RuntimeError(f"Ollama streaming connection failed: {e}") from e
                logger.warning("Ollama stream attempt %d failed. Retrying in %ss...", attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff *= 2.0
            except (httpx.ConnectError, httpx.NetworkError) as e:
                if tokens_yielded or attempt == max_attempts - 1 or (deadline - time.monotonic()) <= (backoff + 1.0):
                    raise RuntimeError(f"Ollama streaming connection failed: {e}") from e
                logger.warning("Ollama stream attempt %d failed (network). Retrying in %ss...", attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff *= 2.0
            except httpx.HTTPError as e:
                if tokens_yielded or attempt == max_attempts - 1 or (deadline - time.monotonic()) <= (backoff + 1.0):
                    raise RuntimeError(f"Ollama streaming connection failed: {e}") from e
                logger.warning("Ollama stream attempt %d failed. Retrying in %ss...", attempt + 1, backoff)
                await asyncio.sleep(backoff)
                backoff *= 2.0

# Store references to unmocked implementations for unit tests
OllamaClient._orig_generate = OllamaClient.generate
OllamaClient._orig_generate_stream = OllamaClient.generate_stream
