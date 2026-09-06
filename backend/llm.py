import os
import logging
from typing import Optional

import ollama

logger = logging.getLogger("MyGPT.LLM")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")


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


def _get_client():
    headers = {}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return ollama.Client(host=OLLAMA_BASE_URL, headers=headers)


def _get_async_client():
    headers = {}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return ollama.AsyncClient(host=OLLAMA_BASE_URL, headers=headers)


def _check_config():
    if not OLLAMA_API_KEY:
        raise LLMError("auth_error", "Ollama API key is not configured.", 401)
    if not OLLAMA_MODEL:
        raise LLMError("bad_request", "Ollama model is not configured.", 400)


def ask_llm(prompt: str, model: Optional[str] = None) -> str:
    _check_config()
    model = model or OLLAMA_MODEL

    try:
        client = _get_client()
        response = client.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            stream=False,
        )
        message = response.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            raise LLMError("unknown", "Ollama returned an empty response.", 502)
        return text
    except LLMError:
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except Exception as exc:
        logger.error(f"Ollama request failed: {exc}")
        raise LLMError("unknown", "Ollama request failed.", 500)


def _encode_image_to_base64(image_path: str) -> str:
    import base64
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ask_llm_with_image(prompt: str, image_path: str, model: Optional[str] = None) -> str:
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
        response = client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            stream=False,
        )
        message = response.get("message", {})
        text = message.get("content", "").strip()
        if not text:
            raise LLMError("unknown", "Ollama returned an empty response.", 502)
        return text
    except LLMError:
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except Exception as exc:
        logger.error(f"Ollama multimodal request failed: {exc}")
        raise LLMError("unknown", "Image analysis failed.", 500)


def stream_llm(prompt: str, model: Optional[str] = None):
    _check_config()
    model = model or OLLAMA_MODEL

    try:
        client = _get_client()
        for response in client.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            stream=True,
        ):
            message = response.get("message", {})
            content = message.get("content", "")
            if content:
                yield content
            if response.get("done"):
                break
    except LLMError:
        raise
    except ollama.ResponseError as exc:
        status = getattr(exc, "status_code", 500)
        if status == 401:
            raise LLMError("auth_error", "Invalid Ollama API key.", 401)
        if status == 402:
            raise LLMError("payment_required", "Ollama model requires a subscription or extra usage.", 402)
        if status == 404:
            raise LLMError("not_found", f"Ollama model '{model}' is not available.", 404)
        raise LLMError("server_error", f"Ollama API error: {status}", status)
    except Exception as exc:
        logger.error(f"Ollama stream failed: {exc}")
        raise LLMError("unknown", "Ollama stream failed.", 500)
