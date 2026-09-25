"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, AsyncGenerator, Generator, Dict, Any
import logging

logger = logging.getLogger("MyGPT.Providers")


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    name: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 60.0
    extra: Optional[Dict[str, Any]] = None


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(
        self,
        kind: str,
        user_message: str,
        status_code: int = 500,
        retry_after: Optional[int] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(user_message)
        self.kind = kind
        self.user_message = user_message
        self.status_code = status_code
        self.retry_after = retry_after
        self.original_exception = original_exception


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self._client = None

    @abstractmethod
    def generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response."""
        pass

    @abstractmethod
    def stream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Generate a streaming response."""
        pass

    @abstractmethod
    async def agenerate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response (async)."""
        pass

    @abstractmethod
    async def astream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response (async)."""
        pass

    def _classify_error(self, exc: Exception) -> ProviderError:
        """Classify an exception into a ProviderError."""
        safe_text = str(exc)
        if self.config.api_key:
            safe_text = safe_text.replace(self.config.api_key, "[REDACTED]")
        safe_text = safe_text.replace("Authorization", "[REDACTED]")
        error_text = safe_text.lower()
        response_status = getattr(getattr(exc, "response", None), "status_code", None)

        if response_status == 401:
            return ProviderError("auth_error", "Invalid API key or authentication failed.", 401, original_exception=exc)
        if response_status == 429:
            return ProviderError("quota_exceeded", "Rate limit or quota exceeded. Please try again later.", 429, retry_after=30, original_exception=exc)
        if response_status in (500, 502, 503, 504):
            return ProviderError("server_error", "The provider service is temporarily unavailable. Please try again later.", 502, original_exception=exc)
        if response_status == 404:
            return ProviderError("not_found", f"Model '{self.config.model}' is not available.", 404, original_exception=exc)

        # Authentication errors
        if any(k in error_text for k in ("401", "unauthorized", "invalid api key", "authentication failed")):
            return ProviderError(
                kind="auth_error",
                user_message="Invalid API key or authentication failed.",
                status_code=401,
                original_exception=exc,
            )

        # Quota/rate limit
        if any(k in error_text for k in ("429", "quota", "rate limit", "resource_exhausted", "too many requests")):
            return ProviderError(
                kind="quota_exceeded",
                user_message="Rate limit or quota exceeded. Please try again later.",
                status_code=429,
                retry_after=30,
                original_exception=exc,
            )

        # Timeout
        if any(k in error_text for k in ("timeout", "timed out", "deadline exceeded")):
            return ProviderError(
                kind="timeout",
                user_message="The request timed out. Please try again.",
                status_code=504,
                original_exception=exc,
            )

        # Connection errors
        if any(k in error_text for k in ("connection", "connect", "network", "resolve", "socket", "unreachable")):
            return ProviderError(
                kind="connection_error",
                user_message="Unable to connect to the provider. Check configuration and network.",
                status_code=503,
                original_exception=exc,
            )

        # Server errors
        if any(k in error_text for k in ("500", "502", "503", "504", "internal server error", "service unavailable", "bad gateway")):
            return ProviderError(
                kind="server_error",
                user_message="The provider service is temporarily unavailable. Please try again later.",
                status_code=502,
                original_exception=exc,
            )

        # Model not found
        if any(k in error_text for k in ("404", "model not found", "model unavailable", "no such model")):
            return ProviderError(
                kind="not_found",
                user_message=f"Model '{self.config.model}' is not available.",
                status_code=404,
                original_exception=exc,
            )

        # Default
        return ProviderError(
            kind="unknown_error",
            user_message=f"Provider error: {safe_text}",
            status_code=500,
            original_exception=exc,
        )

    def _log_safe(self, level: int, message: str, **kwargs):
        """Log without exposing secrets."""
        safe_kwargs = {
            k: v for k, v in kwargs.items()
            if k not in ("api_key", "key", "secret", "token", "password")
        }
        logger.log(level, message, extra=safe_kwargs)

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name for logging."""
        pass