"""LLM interface for MyGPT — routes through the multi-provider registry."""

import os
import base64
import logging
from typing import Optional, Generator, AsyncGenerator

from dotenv import load_dotenv

load_dotenv()

from providers.base import ProviderError
from providers.registry import (
    configure_providers_from_env,
    get_routed_provider_metadata,
)

logger = logging.getLogger("MyGPT.LLM")


# ---------------------------------------------------------------------------
# NVIDIA configuration
# ---------------------------------------------------------------------------

NVIDIA_TEXT_MODEL = os.getenv(
    "NVIDIA_TEXT_MODEL",
    "deepseek-ai/deepseek-v4-flash",
)

NVIDIA_VISION_MODEL = os.getenv(
    "NVIDIA_VISION_MODEL",
    "deepseek-ai/deepseek-v4.1-flash",
)

NVIDIA_TEMPERATURE = float(
    os.getenv("NVIDIA_TEMPERATURE", "0.2")
)

NVIDIA_TOP_P = float(
    os.getenv("NVIDIA_TOP_P", "0.9")
)

NVIDIA_NUM_PREDICT = int(
    os.getenv("NVIDIA_NUM_PREDICT", "4096")
)

NVIDIA_TIMEOUT = float(
    os.getenv("NVIDIA_TIMEOUT", "60")
)

# Backward-compatible alias.
# app.py currently imports OLLAMA_MODEL.
OLLAMA_MODEL = NVIDIA_TEXT_MODEL


# ---------------------------------------------------------------------------
# Output limits
# ---------------------------------------------------------------------------

NUM_PREDICT_SHORT = 256
NUM_PREDICT_NORMAL = 2048
NUM_PREDICT_RAG = 2048
NUM_PREDICT_LONG = 4096


_SHORT_PATTERNS = (
    "what is 2+2",
    "what is 3+3",
    "what is 4+4",
    "what is 5+5",
    "what is 6+6",
    "what is 7+7",
    "what is 8+8",
    "what is 9+9",
    "what is 10+10",
    "what is 2*2",
    "what is 3*3",
    "what is the time",
    "what time is it",
    "what is today's date",
    "what day is today",
    "what is the weather",
    "2+2",
    "3+3",
    "4+4",
    "5+5",
    "calculate",
    "compute",
)

_LONG_PATTERNS = (
    "explain in detail",
    "in depth",
    "comprehensive",
    "analyze thoroughly",
    "step by step",
    "walk through",
    "compare and contrast",
    "pros and cons",
    "write a",
    "create a",
    "implement a",
    "design a",
    "build a",
)

_RAG_FACTUAL_PATTERNS = (
    "what is the output",
    "what is the result",
    "what does this print",
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
    """Return a request-aware generation limit."""

    env_limit = NVIDIA_NUM_PREDICT
    msg_lower = (message or "").lower().strip()

    if action == "rag":
        if any(p in msg_lower for p in _LONG_PATTERNS):
            requested = NUM_PREDICT_LONG
        elif any(p in msg_lower for p in _RAG_FACTUAL_PATTERNS):
            requested = NUM_PREDICT_NORMAL
        elif any(p in msg_lower for p in _RAG_EXPLAIN_PATTERNS):
            requested = NUM_PREDICT_RAG
        else:
            requested = NUM_PREDICT_NORMAL

    elif action in ("python", "time", "web"):
        requested = NUM_PREDICT_SHORT

    elif action == "chat":
        if any(p in msg_lower for p in _SHORT_PATTERNS):
            requested = NUM_PREDICT_SHORT
        elif any(p in msg_lower for p in _LONG_PATTERNS):
            requested = NUM_PREDICT_LONG
        else:
            requested = NUM_PREDICT_NORMAL

    elif action in (
        "code",
        "code_explanation",
        "web_research",
        "current_info",
        "general_knowledge",
        "math",
        "creative",
    ):
        requested = NUM_PREDICT_NORMAL

    else:
        requested = NUM_PREDICT_NORMAL

    return min(requested, env_limit)


# ---------------------------------------------------------------------------
# Error compatibility layer
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Compatibility exception used by the rest of the MyGPT backend."""

    def __init__(
        self,
        kind,
        user_message,
        status_code=500,
        retry_after=None,
    ):
        super().__init__(user_message)

        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code
        self.retry_after = retry_after


def _provider_to_llm_error(exc: ProviderError) -> LLMError:
    """Convert ProviderError into the legacy LLMError contract."""

    return LLMError(
        exc.kind,
        exc.user_message,
        exc.status_code,
        exc.retry_after,
    )


_provider_registry = None


def _get_registry():
    """Return the configured provider registry."""

    global _provider_registry

    if _provider_registry is None:
        _provider_registry = configure_providers_from_env()

    return _provider_registry


def _check_config():
    """Validate that a provider is configured (no-op in test contexts)."""

    registry = _get_registry()
    if registry.get_primary() is None:
        raise LLMError(
            "provider_not_configured",
            "No LLM provider is configured.",
            503,
        )


# ---------------------------------------------------------------------------
# Basic non-streaming generation
# ---------------------------------------------------------------------------

def ask_llm(
    prompt: str,
    model: Optional[str] = None,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> str:
    """Generate a response using the configured LLM provider."""

    registry = _get_registry()

    try:
        if perf_context is not None:
            try:
                perf_context.mark_ollama_start()
            except Exception:
                pass

        kwargs = {}

        if model:
            kwargs["model"] = model

        result = registry.execute_with_fallback(
            "generate",
            prompt,
            num_predict=num_predict or get_num_predict("chat", prompt),
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
            **kwargs,
        )

        if not result or not str(result).strip():
            raise LLMError(
                "unknown",
                "NVIDIA returned an empty response.",
                502,
            )

        result = str(result).strip()

        if perf_context is not None:
            try:
                perf_context.mark_done({
                    "ttft_ms": 0.0,
                    "total_ms": 0.0,
                    "prompt_eval_count": 0,
                    "prompt_eval_duration_ms": 0.0,
                    "eval_count": 0,
                    "eval_duration_ms": 0.0,
                })
            except Exception:
                pass

        return result

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        logger.exception("NVIDIA ask_llm failed")

        if perf_context is not None:
            try:
                perf_context.add_error("llm_error")
                perf_context.emit()
            except Exception:
                pass

        raise LLMError(
            "connection_error",
            "NVIDIA provider failed to generate a response.",
            503,
        ) from exc


# ---------------------------------------------------------------------------
# Streaming generation
# ---------------------------------------------------------------------------

def stream_llm(
    prompt: str,
    model: Optional[str] = None,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> Generator[str, None, None]:
    """Stream a response using the configured LLM provider."""

    registry = _get_registry()

    kwargs = {}

    if model:
        kwargs["model"] = model

    try:
        stream = registry.execute_with_fallback(
            "stream_generate",
            prompt,
            num_predict=num_predict or get_num_predict("chat", prompt),
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
            **kwargs,
        )

        emitted = False

        for chunk in stream:
            if chunk:
                emitted = True
                yield chunk

        if not emitted:
            raise LLMError(
                "unknown",
                "NVIDIA returned an empty streaming response.",
                502,
            )

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        logger.exception("NVIDIA stream_llm failed")

        raise LLMError(
            "connection_error",
            "NVIDIA provider failed during streaming.",
            503,
        ) from exc


# ---------------------------------------------------------------------------
# Routed generation
# ---------------------------------------------------------------------------

def ask_llm_routed(
    prompt: str,
    action: str,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> str:
    """Route a generation request through the provider registry."""

    registry = _get_registry()

    try:
        limit = num_predict or get_num_predict(
            action,
            prompt,
        )

        return registry.execute_with_fallback(
            "generate",
            prompt,
            num_predict=limit,
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
        )

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        logger.exception(
            "NVIDIA routed generation failed"
        )

        raise LLMError(
            "connection_error",
            "NVIDIA provider failed to generate a response.",
            503,
        ) from exc


def stream_llm_routed(
    prompt: str,
    action: str,
    perf_context=None,
    num_predict: Optional[int] = None,
):
    """Stream a routing request through the provider registry."""

    registry = _get_registry()

    try:
        limit = num_predict or get_num_predict(
            action,
            prompt,
        )

        stream = registry.execute_with_fallback(
            "stream_generate",
            prompt,
            num_predict=limit,
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
        )

        for chunk in stream:
            if chunk:
                yield chunk

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        logger.exception(
            "NVIDIA routed streaming failed"
        )

        raise LLMError(
            "connection_error",
            "NVIDIA provider failed during streaming.",
            503,
        ) from exc


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------

def _encode_image_to_base64(
    image_path: str,
) -> str:
    """Read an image file and encode it as base64."""

    with open(image_path, "rb") as file:
        return base64.b64encode(
            file.read()
        ).decode("utf-8")


def ask_llm_with_image(
    prompt: str,
    image_path: str,
    model: Optional[str] = None,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> str:
    """Analyze an image using the configured provider's vision model."""

    if not image_path or not os.path.exists(image_path):
        raise LLMError(
            "bad_request",
            "Invalid image path.",
            400,
        )

    try:
        image_b64 = _encode_image_to_base64(
            image_path
        )
    except Exception as exc:
        logger.exception(
            "Failed to read image"
        )
        raise LLMError(
            "bad_request",
            "Unable to read the image file.",
            400,
        ) from exc

    registry = _get_registry()

    vision_model = (
        model
        or NVIDIA_VISION_MODEL
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            "data:image/*;base64,"
                            + image_b64
                        )
                    },
                },
            ],
        }
    ]

    try:
        result = registry.execute_with_fallback(
            "generate",
            "",
            num_predict=num_predict or NUM_PREDICT_NORMAL,
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
            model=vision_model,
            vision=True,
            messages=messages,
        )

        if not result or not str(result).strip():
            raise LLMError(
                "unknown",
                "NVIDIA returned an empty vision response.",
                502,
            )

        return str(result).strip()

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        logger.exception(
            "NVIDIA vision request failed"
        )

        raise LLMError(
            "connection_error",
            "NVIDIA vision analysis failed.",
            503,
        ) from exc


# ---------------------------------------------------------------------------
# Async compatibility functions
# ---------------------------------------------------------------------------

async def aask_llm(
    prompt: str,
    model: Optional[str] = None,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> str:
    """Async generation via the provider registry."""

    registry = _get_registry()

    kwargs = {}

    if model:
        kwargs["model"] = model

    try:
        result = await registry.aexecute_with_fallback(
            "agenerate",
            prompt,
            num_predict=num_predict or get_num_predict("chat", prompt),
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
            **kwargs,
        )

        if not result or not str(result).strip():
            raise LLMError(
                "unknown",
                "NVIDIA returned an empty response.",
                502,
            )

        return str(result).strip()

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        raise LLMError(
            "connection_error",
            "NVIDIA provider failed to generate a response.",
            503,
        ) from exc


async def astream_llm_routed(
    prompt: str,
    action: str,
    perf_context=None,
    num_predict: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Async streaming via the provider registry."""

    registry = _get_registry()

    try:
        limit = num_predict or get_num_predict(
            action,
            prompt,
        )

        stream = await registry.aexecute_with_fallback(
            "astream_generate",
            prompt,
            num_predict=limit,
            temperature=NVIDIA_TEMPERATURE,
            top_p=NVIDIA_TOP_P,
            primary_only=False,
        )

        async for chunk in stream:
            if chunk:
                yield chunk

    except ProviderError as exc:
        raise _provider_to_llm_error(exc) from exc

    except LLMError:
        raise

    except Exception as exc:
        raise LLMError(
            "connection_error",
            "NVIDIA provider failed during async streaming.",
            503,
        ) from exc


# ---------------------------------------------------------------------------
# Safe startup helper
# ---------------------------------------------------------------------------

def get_provider_status():
    """Return safe provider status without exposing secrets."""

    provider_name, provider_model = get_routed_provider_metadata()

    return {
        "provider": provider_name,
        "model": provider_model,
        "configured": provider_name != "unknown",
    }
