"""Gemini provider implementation."""

import os
import time
import logging
from typing import Optional, Generator, AsyncGenerator, Dict, Any

from providers.base import LLMProvider, ProviderConfig, ProviderError

logger = logging.getLogger("MyGPT.Providers.Gemini")


class GeminiProvider(LLMProvider):
    """Gemini provider using Google GenAI SDK."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None
        self._max_retries = self.config.extra.get("max_retries", 2) if self.config.extra else 2
        self._base_delay = self.config.extra.get("base_delay", 1.0) if self.config.extra else 1.0
        self._max_delay = self.config.extra.get("max_delay", 8.0) if self.config.extra else 8.0

    def _get_client(self):
        if self._client is None:
            if not self.config.api_key:
                raise ProviderError(
                    kind="auth_error",
                    user_message="Gemini API key is not configured.",
                    status_code=401,
                )
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _is_retryable(self, exc: Exception) -> bool:
        """Check if an exception is retryable."""
        error_text = str(exc).lower()
        return any(k in error_text for k in (
            "503", "429", "quota", "resource_exhausted", "unavailable",
            "timeout", "timed out", "deadline exceeded",
            "connection", "connect", "network", "resolve", "socket"
        ))

    def _retry_with_backoff(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        import random
        delay = min(self._base_delay * (2 ** attempt), self._max_delay)
        return delay * (0.5 + random.random())

    def generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response via Gemini."""
        if not self.config.api_key:
            raise ProviderError(
                kind="auth_error",
                user_message="Gemini API key is not configured.",
                status_code=401,
            )

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                client = self._get_client()
                self._log_safe(logging.INFO, "Gemini generate request", model=self.config.model)
                from google.genai import types
                response = client.models.generate_content(
                    model=self.config.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        top_p=top_p,
                        max_output_tokens=num_predict or 8192,
                    ),
                )
                text = getattr(response, "text", None)
                if not text:
                    raise ProviderError(
                        kind="empty_response",
                        user_message="Gemini returned an empty response.",
                        status_code=502,
                    )
                return text.strip()
            except ProviderError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini request attempt %d/%d failed: %s", attempt + 1, self._max_retries + 1, exc)
                if attempt < self._max_retries and self._is_retryable(exc):
                    delay = self._retry_with_backoff(attempt)
                    logger.info("Retrying Gemini in %.2f seconds...", delay)
                    time.sleep(delay)
                    continue
                raise self._classify_error(exc) from exc

        raise ProviderError(
            kind="connection_error",
            user_message=f"Gemini request failed after retries: {last_error}",
            status_code=503,
        )

    def stream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Generate a streaming response via Gemini."""
        if not self.config.api_key:
            raise ProviderError(
                kind="auth_error",
                user_message="Gemini API key is not configured.",
                status_code=401,
            )

        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                client = self._get_client()
                self._log_safe(logging.INFO, "Gemini stream request", model=self.config.model)
                from google.genai import types
                response = client.models.generate_content_stream(
                    model=self.config.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        top_p=top_p,
                        max_output_tokens=num_predict or 8192,
                    ),
                )
                for chunk in response:
                    text = getattr(chunk, "text", None)
                    if text:
                        yield text
                return
            except ProviderError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini stream attempt %d/%d failed: %s", attempt + 1, self._max_retries + 1, exc)
                if attempt < self._max_retries and self._is_retryable(exc):
                    delay = self._retry_with_backoff(attempt)
                    logger.info("Retrying Gemini stream in %.2f seconds...", delay)
                    time.sleep(delay)
                    continue
                raise self._classify_error(exc) from exc

        raise ProviderError(
            kind="connection_error",
            user_message=f"Gemini stream failed after retries: {last_error}",
            status_code=503,
        )

    async def agenerate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response via Gemini (async)."""
        # For now, delegate to sync version since google-genai doesn't have native async
        return self.generate(prompt, num_predict, temperature, top_p, **kwargs)

    async def astream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response via Gemini (async)."""
        # For now, delegate to sync version
        for chunk in self.stream_generate(prompt, num_predict, temperature, top_p, **kwargs):
            yield chunk