import os
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import ollama
from agents.prompts import SYSTEM_PROMPT
from providers.base import ProviderError
from providers.registry import configure_providers_from_env

logger = logging.getLogger("MyGPT.LLM")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_CODE_MODEL = os.getenv("OLLAMA_CODE_MODEL", "codellama:7b")

# Gemini configuration for stronger model routing
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")

_gemini_client = None
_provider_registry = None


def get_routed_provider_metadata() -> tuple[str | None, str | None]:
    """Return safe active routing metadata for request diagnostics."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = configure_providers_from_env()

    primary_name = _provider_registry._primary_provider
    primary = (
        _provider_registry._providers.get(primary_name)
        if primary_name
        else None
    )
    config = getattr(primary, "config", None)
    return primary_name, getattr(config, "model", None)

# Gemini retry configuration
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
GEMINI_BASE_DELAY = float(os.getenv("GEMINI_BASE_DELAY", "1.0"))  # seconds
GEMINI_MAX_DELAY = float(os.getenv("GEMINI_MAX_DELAY", "8.0"))    # seconds

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


OLLAMA_TEMPERATURE = _env_float("OLLAMA_TEMPERATURE", 0.2)
OLLAMA_TOP_P = _env_float("OLLAMA_TOP_P", 0.9)
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 4096)
OLLAMA_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 768)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")


# ---------------------------------------------------------------------------
# Smart output-limit selection
# ---------------------------------------------------------------------------
# Request-aware generation limits. The environment variable OLLAMA_NUM_PREDICT
# remains the global fallback and caps every request.
#
# Policy:
#   short factual / math       -> 64
#   normal chat                -> 512
#   RAG simple factual/output  -> 512
#   RAG code explanation/review -> 512
#   RAG deep/long analysis     -> 768
#   long analysis              -> 768

NUM_PREDICT_SHORT = 64
NUM_PREDICT_NORMAL = 512
NUM_PREDICT_RAG = 512
NUM_PREDICT_LONG = 768

# Patterns that indicate a very short factual or math question.
_SHORT_PATTERNS = (
    "what is 2+2", "what is 3+3", "what is 4+4", "what is 5+5",
    "what is 6+6", "what is 7+7", "what is 8+8", "what is 9+9",
    "what is 10+10", "what is 2*2", "what is 3*3",
    "what is the time", "what time is it",
    "what is today's date", "what day is today",
    "what is the weather",
    "2+2", "3+3", "4+4", "5+5",
    "calculate", "compute",
)

# Patterns that indicate a longer analysis request.
_LONG_PATTERNS = (
    "explain in detail", "in depth", "comprehensive",
    "analyze thoroughly", "step by step", "walk through",
    "compare and contrast", "pros and cons",
    "write a", "create a", "implement a",
    "design a", "build a",
)

# RAG patterns that indicate a simple factual/output/value question.
# These need precise short answers and should not use the longer 768 limit.
_RAG_FACTUAL_PATTERNS = (
    "what is the output",
    "what is the result",
    "what does this print",
    "what does i  t print",
    "what is the value",
    "what is the answer",
    "what is the return value",
    "what is returned",
    "what's the output",
    "what's the result",
    "what's the value",
    "output of",
    "result of",
    "value of",
    "return value",
)

# RAG patterns that indicate code explanation/review/analysis.
# These benefit from the larger normal response limit.
_RAG_EXPLAIN_PATTERNS = (
    "explain this code",
    "explain the code",
    "explain how this code works",
    "review this code",
    "analyze this code",
    "what does this code do",
    "how does this code work",
    "what does this function do",
    "what does this script do",
    "what does this file do",
    "find any problems",
    "find any issues",
    "problems in this code",
    "bug in this",
    "error in this code",
    "what's wrong with this code",
    "is there a bug",
    "is there an error",
    "code review",
    "review the code",
)


def get_num_predict(action: str, message: str) -> int:
    """Return a request-aware generation limit.

    The environment variable OLLAMA_NUM_PREDICT caps the result.
    """
    env_limit = OLLAMA_NUM_PREDICT
    msg_lower = message.lower().strip()

    # Determine the requested limit based on action and message content.
    if action == "rag":
        # Check for long analysis within RAG requests.
        if any(p in msg_lower for p in _LONG_PATTERNS):
            requested = NUM_PREDICT_LONG
        # Check for simple factual/output questions — these need precise
        # short answers and should not use the longer 768 limit.
        elif any(p in msg_lower for p in _RAG_FACTUAL_PATTERNS):
            requested = NUM_PREDICT_NORMAL
        # Check for code explanation/review/analysis.
        elif any(p in msg_lower for p in _RAG_EXPLAIN_PATTERNS):
            requested = NUM_PREDICT_RAG
        else:
            # Default RAG: use normal limit for unknown RAG questions.
            requested = NUM_PREDICT_NORMAL
    elif action in ("python", "time", "web"):
        # Tool actions tend to produce short, deterministic answers.
        requested = NUM_PREDICT_SHORT
    elif action == "chat":
        # Check for very short factual/math questions.
        if any(p in msg_lower for p in _SHORT_PATTERNS):
            requested = NUM_PREDICT_SHORT
        elif any(p in msg_lower for p in _LONG_PATTERNS):
            requested = NUM_PREDICT_LONG
        else:
            requested = NUM_PREDICT_NORMAL
    else:
        requested = NUM_PREDICT_NORMAL

    # Never exceed the environment-configured maximum.
    return min(requested, env_limit)


class LLMError(Exception):
    def __init__(self, kind, user_message, status_code=500, retry_after=None):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code
        self.retry_after = retry_after


def _mask_key(key: str) -> str:
    if not key:
        return "<missing>"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _is_local_ollama() -> bool:
    hostname = urlparse(OLLAMA_BASE_URL).hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _get_headers():
    if _is_local_ollama() or not OLLAMA_API_KEY:
        return {}
    return {"Authorization": f"Bearer {OLLAMA_API_KEY}"}


# Cache a single Ollama client so HTTP connections are reused across
# requests instead of being re-established on every call.
_sync_client = None
_async_client = None


def _get_client():
    global _sync_client
    if _sync_client is None:
        headers = _get_headers()
        if headers:
            _sync_client = ollama.Client(host=OLLAMA_BASE_URL, headers=headers)
        else:
            _sync_client = ollama.Client(host=OLLAMA_BASE_URL)
    return _sync_client


def _get_async_client():
    global _async_client
    if _async_client is None:
        headers = _get_headers()
        if headers:
            _async_client = ollama.AsyncClient(host=OLLAMA_BASE_URL, headers=headers)
        else:
            _async_client = ollama.AsyncClient(host=OLLAMA_BASE_URL)
    return _async_client


# --- Gemini Client ---
def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            raise LLMError("auth_error", "Gemini API key is not configured.", 401)
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _check_config():
    if not _is_local_ollama() and not OLLAMA_API_KEY:
        raise LLMError("auth_error", "Ollama API key is required for the configured remote Ollama host.", 401)
    if not OLLAMA_MODEL:
        raise LLMError("bad_request", "Ollama model is not configured.", 400)


def _chat_messages(prompt: str, images=None):
    user_message = {"role": "user", "content": prompt}
    if images:
        user_message["images"] = images
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        user_message,
    ]


def _generation_options(num_predict: Optional[int] = None):
    """Build Ollama generation options.

    If num_predict is provided it overrides the default; the result is
    always capped by the environment-configured OLLAMA_NUM_PREDICT.

    Stop sequences prevent the model from generating new prompt sections.
    """
    limit = num_predict if num_predict is not None else OLLAMA_NUM_PREDICT
    return {
        "temperature": OLLAMA_TEMPERATURE,
        "top_p": OLLAMA_TOP_P,
        "num_ctx": OLLAMA_NUM_CTX,
        "num_predict": limit,
        "stop": [
            "### Current User Request",
            "### Assistant Response",
            "### Long-Term User Memory",
            "### Recent Conversation History",
            "### Document & Knowledge Context",
            "### Autonomous Tool Observations",
            "### Context Safety",
        ],
    }


def _connection_error(operation: str, exc: Exception) -> LLMError:
    logger.error("Ollama %s failed: %s", operation, exc)
    if _is_local_ollama():
        message = (
            f"Unable to connect to local Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running and the model is available."
        )
    else:
        message = "Unable to connect to Ollama. Check OLLAMA_BASE_URL and the Ollama service."
    return LLMError("connection_error", message, 503)


def _extract_ollama_metrics(response: dict) -> dict:
    """Extract Ollama timing metrics from a non-streaming response."""
    return {
        "ttft_ms": 0.0,
        "total_ms": 0.0,
        "prompt_eval_count": response.get("prompt_eval_count", 0),
        "prompt_eval_duration_ms": (response.get("prompt_eval_duration", 0) / 1e6),
        "eval_count": response.get("eval_count", 0),
        "eval_duration_ms": (response.get("eval_duration", 0) / 1e6),
    }


def ask_llm(prompt: str, model: Optional[str] = None, perf_context=None, num_predict: Optional[int] = None) -> str:
    _check_config()
    model = model or OLLAMA_MODEL

    try:
        client = _get_client()
        if perf_context is not None:
            perf_context.mark_ollama_start()
        response = client.chat(
            model=model,
            messages=_chat_messages(prompt),
            stream=False,
            options=_generation_options(num_predict),
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        message = response.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            raise LLMError("unknown", "Ollama returned an empty response.", 502)
        if perf_context is not None:
            perf_context.mark_done(_extract_ollama_metrics(response))
        return text
    except LLMError:
        if perf_context is not None:
            perf_context.add_error("llm_error")
            perf_context.emit()
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            if perf_context is not None:
                perf_context.add_error("auth_error")
                perf_context.emit()
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            if perf_context is not None:
                perf_context.add_error("payment_required")
                perf_context.emit()
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            if perf_context is not None:
                perf_context.add_error("not_found")
                perf_context.emit()
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        if perf_context is not None:
            perf_context.add_error("server_error")
            perf_context.emit()
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except ollama.RequestError as exc:
        if perf_context is not None:
            perf_context.add_error("connection_error")
            perf_context.emit()
        raise _connection_error("request", exc) from exc
    except Exception as exc:
        if perf_context is not None:
            perf_context.add_error("unknown_error")
            perf_context.emit()
        raise _connection_error("request", exc) from exc


# --- Model Routing ---
def _get_model_for_action(action: str) -> tuple[str, str]:
    """
    Determine the best model/provider for a given action.
    Returns (provider, model_name) where provider is 'ollama' or 'gemini'.
    """
    # For code generation, prefer Gemini if available, else Ollama code model
    if action == "code":
        if GEMINI_API_KEY:
            return "gemini", GEMINI_TEXT_MODEL
        return "ollama", OLLAMA_CODE_MODEL
    
    # For code explanation, complex analysis - use stronger model if available
    if action in ("code_explanation", "web", "web_research", "current_info"):
        if GEMINI_API_KEY:
            return "gemini", GEMINI_TEXT_MODEL
    
    # Default to Ollama
    return "ollama", OLLAMA_MODEL


def ask_gemini(prompt: str, perf_context=None, action: Optional[str] = None) -> str:
    """Generate text using Gemini model with bounded retries."""
    if not GEMINI_API_KEY:
        raise LLMError("auth_error", "Gemini API key is not configured.", 401)
    
    last_error = None
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        try:
            client = _get_gemini_client()
            if perf_context is not None:
                perf_context.mark_ollama_start()  # Reuse timing field
            from google.genai import types
            response = client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.9,
                    max_output_tokens=8192,
                ),
            )
            text = getattr(response, "text", None)
            if not text:
                raise LLMError("unknown", "Gemini returned an empty response.", 502)
            if perf_context is not None:
                # Gemini doesn't provide detailed metrics like Ollama
                perf_context.mark_done({
                    "ttft_ms": 0.0,
                    "total_ms": 0.0,
                    "prompt_eval_count": 0,
                    "prompt_eval_duration_ms": 0.0,
                    "eval_count": 0,
                    "eval_duration_ms": 0.0,
                })
            return text.strip()
        except LLMError:
            if perf_context is not None:
                perf_context.add_error("llm_error")
                perf_context.emit()
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini request attempt %d/%d failed: %s", attempt + 1, GEMINI_MAX_RETRIES + 1, exc)
            
            # Check if this is a retryable error (503, 429, timeout, network)
            error_text = str(exc).lower()
            is_retryable = any(k in error_text for k in (
                "503", "429", "quota", "resource_exhausted", "unavailable", 
                "timeout", "timed out", "deadline exceeded",
                "connection", "connect", "network", "resolve", "socket"
            ))
            
            if attempt < GEMINI_MAX_RETRIES and is_retryable:
                # Exponential backoff with jitter
                delay = min(GEMINI_BASE_DELAY * (2 ** attempt), GEMINI_MAX_DELAY)
                import random
                delay = delay * (0.5 + random.random())  # jitter
                logger.info("Retrying Gemini in %.2f seconds...", delay)
                time.sleep(delay)
                continue
            
            if perf_context is not None:
                perf_context.add_error("unknown_error")
                perf_context.emit()
            logger.error("Gemini request failed after %d attempts: %s", attempt + 1, exc)
            raise LLMError("connection_error", f"Gemini request failed: {exc}", 503)
    
    # Should not reach here, but just in case
    raise LLMError("connection_error", f"Gemini request failed after retries: {last_error}", 503)


def ask_llm_routed(prompt: str, action: str, perf_context=None, num_predict: Optional[int] = None) -> str:
    """Route through the configured provider registry."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = configure_providers_from_env()

    try:
        return _provider_registry.execute_with_fallback(
            "generate",
            prompt,
            num_predict=num_predict,
            temperature=OLLAMA_TEMPERATURE,
            top_p=OLLAMA_TOP_P,
            primary_only=(action == "current_info"),
        )
    except ProviderError as exc:
        if action == "current_info":
            raise LLMError(
                "current_info_failed",
                "Unable to synthesize current information. The search results are available but the AI synthesis service is unavailable.",
                503,
                retry_after=30,
            ) from exc
        raise LLMError(exc.kind, exc.user_message, exc.status_code, exc.retry_after) from exc


def _encode_image_to_base64(image_path: str) -> str:
    import base64
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ask_llm_with_image(prompt: str, image_path: str, model: Optional[str] = None, perf_context=None, num_predict: Optional[int] = None) -> str:
    _check_config()
    model = model or OLLAMA_MODEL

    if not image_path or not os.path.exists(image_path):
        raise LLMError("bad_request", "Invalid image path.", 400)

    try:
        image_b64 = _encode_image_to_base64(image_path)
    except Exception as exc:
        logger.error(f"Failed to read image: {exc}")
        raise LLMError("bad_request", "Unable to read the image file.", 400)

    try:
        client = _get_client()
        if perf_context is not None:
            perf_context.mark_ollama_start()
        response = client.chat(
            model=model,
            messages=_chat_messages(prompt, [image_b64]),
            stream=False,
            options=_generation_options(num_predict),
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        message = response.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            raise LLMError("unknown", "Ollama returned an empty response.", 502)
        if perf_context is not None:
            perf_context.mark_done(_extract_ollama_metrics(response))
        return text
    except LLMError:
        if perf_context is not None:
            perf_context.add_error("llm_error")
            perf_context.emit()
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            if perf_context is not None:
                perf_context.add_error("auth_error")
                perf_context.emit()
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            if perf_context is not None:
                perf_context.add_error("payment_required")
                perf_context.emit()
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            if perf_context is not None:
                perf_context.add_error("not_found")
                perf_context.emit()
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        if perf_context is not None:
            perf_context.add_error("server_error")
            perf_context.emit()
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except ollama.RequestError as exc:
        if perf_context is not None:
            perf_context.add_error("connection_error")
            perf_context.emit()
        raise _connection_error("image request", exc) from exc
    except Exception as exc:
        if perf_context is not None:
            perf_context.add_error("unknown_error")
            perf_context.emit()
        raise _connection_error("image request", exc) from exc


def stream_llm(prompt: str, model: Optional[str] = None, perf_context=None, num_predict: Optional[int] = None):
    _check_config()
    model = model or OLLAMA_MODEL

    try:
        client = _get_client()
        if perf_context is not None:
            perf_context.mark_ollama_start()
        t_first = None
        first_token_time = None
        ollama_metrics = {}
        for response in client.chat(
            model=model,
            messages=_chat_messages(prompt),
            stream=True,
            options=_generation_options(num_predict),
            keep_alive=OLLAMA_KEEP_ALIVE,
        ):
            message = response.get("message", {})
            content = message.get("content", "")
            if content:
                if t_first is None:
                    t_first = time.perf_counter()
                    first_token_time = (t_first - perf_context.ollama_start_time) * 1000 if perf_context else 0
                yield content
            if response.get("done"):
                ollama_metrics = {
                    "ttft_ms": first_token_time or 0,
                    "total_ms": (time.perf_counter() - perf_context.ollama_start_time) * 1000 if perf_context else 0,
                    "prompt_eval_count": response.get("prompt_eval_count", 0),
                    "prompt_eval_duration_ms": (response.get("prompt_eval_duration", 0) / 1e6),
                    "eval_count": response.get("eval_count", 0),
                    "eval_duration_ms": (response.get("eval_duration", 0) / 1e6),
                }
                break
        if perf_context is not None:
            perf_context.mark_done(ollama_metrics)
            perf_context.emit()
    except LLMError:
        if perf_context is not None:
            perf_context.add_error("llm_error")
            perf_context.emit()
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            if perf_context is not None:
                perf_context.add_error("auth_error")
                perf_context.emit()
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            if perf_context is not None:
                perf_context.add_error("payment_required")
                perf_context.emit()
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            if perf_context is not None:
                perf_context.add_error("not_found")
                perf_context.emit()
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        if perf_context is not None:
            perf_context.add_error("server_error")
            perf_context.emit()
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except ollama.RequestError as exc:
        if perf_context is not None:
            perf_context.add_error("connection_error")
            perf_context.emit()
        raise _connection_error("stream request", exc) from exc
    except Exception as exc:
        if perf_context is not None:
            perf_context.add_error("unknown_error")
            perf_context.emit()
        raise _connection_error("stream request", exc) from exc


def stream_gemini(prompt: str, perf_context=None, action: Optional[str] = None):
    """Stream text using Gemini model with bounded retries."""
    if not GEMINI_API_KEY:
        raise LLMError("auth_error", "Gemini API key is not configured.", 401)
    
    last_error = None
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        try:
            client = _get_gemini_client()
            if perf_context is not None:
                perf_context.mark_ollama_start()
            from google.genai import types
            response = client.models.generate_content_stream(
                model=GEMINI_TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.9,
                    max_output_tokens=8192,
                ),
            )
            first_chunk = True
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    if first_chunk and perf_context is not None:
                        # Mark first token time
                        perf_context.mark_done({
                            "ttft_ms": (time.perf_counter() - perf_context.ollama_start_time) * 1000,
                            "total_ms": 0.0,
                            "prompt_eval_count": 0,
                            "prompt_eval_duration_ms": 0.0,
                            "eval_count": 0,
                            "eval_duration_ms": 0.0,
                        })
                        first_chunk = False
                    yield text
            if perf_context is not None:
                perf_context.mark_done({
                    "ttft_ms": 0.0,
                    "total_ms": (time.perf_counter() - perf_context.ollama_start_time) * 1000,
                    "prompt_eval_count": 0,
                    "prompt_eval_duration_ms": 0.0,
                    "eval_count": 0,
                    "eval_duration_ms": 0.0,
                })
                perf_context.emit()
            return
        except LLMError:
            if perf_context is not None:
                perf_context.add_error("llm_error")
                perf_context.emit()
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini stream attempt %d/%d failed: %s", attempt + 1, GEMINI_MAX_RETRIES + 1, exc)
            
            error_text = str(exc).lower()
            is_retryable = any(k in error_text for k in (
                "503", "429", "quota", "resource_exhausted", "unavailable", 
                "timeout", "timed out", "deadline exceeded",
                "connection", "connect", "network", "resolve", "socket"
            ))
            
            if attempt < GEMINI_MAX_RETRIES and is_retryable:
                delay = min(GEMINI_BASE_DELAY * (2 ** attempt), GEMINI_MAX_DELAY)
                import random
                delay = delay * (0.5 + random.random())
                logger.info("Retrying Gemini stream in %.2f seconds...", delay)
                time.sleep(delay)
                continue
            
            if perf_context is not None:
                perf_context.add_error("unknown_error")
                perf_context.emit()
            logger.error("Gemini stream request failed after %d attempts: %s", attempt + 1, exc)
            raise LLMError("connection_error", f"Gemini stream failed: {exc}", 503)
    
    raise LLMError("connection_error", f"Gemini stream failed after retries: {last_error}", 503)


def stream_llm_routed(prompt: str, action: str, perf_context=None, num_predict: Optional[int] = None):
    """Route streaming through the configured provider registry."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = configure_providers_from_env()

    try:
        yield from _provider_registry.execute_with_fallback(
            "stream_generate",
            prompt,
            num_predict=num_predict,
            temperature=OLLAMA_TEMPERATURE,
            top_p=OLLAMA_TOP_P,
            primary_only=(action == "current_info"),
        )
    except ProviderError as exc:
        if action == "current_info":
            raise LLMError(
                "current_info_failed",
                "Unable to synthesize current information. The search results are available but the AI synthesis service is unavailable.",
                503,
                retry_after=30,
            ) from exc
        raise LLMError(exc.kind, exc.user_message, exc.status_code, exc.retry_after) from exc
