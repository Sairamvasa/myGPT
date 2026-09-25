"""Ollama provider implementation."""

import os
import time
import logging
from typing import Optional, Generator, AsyncGenerator, Dict, Any
from urllib.parse import urlparse

import ollama

from providers.base import LLMProvider, ProviderConfig, ProviderError

logger = logging.getLogger("MyGPT.Providers.Ollama")


class OllamaProvider(LLMProvider):
    """Ollama provider for local/remote Ollama models."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._sync_client: Optional[ollama.Client] = None
        self._async_client: Optional[ollama.AsyncClient] = None
        self._system_prompt = self._get_system_prompt()

    def _get_system_prompt(self) -> str:
        """Get the system prompt from the agents module."""
        try:
            from agents.prompts import SYSTEM_PROMPT
            return SYSTEM_PROMPT
        except ImportError:
            return "You are a helpful AI assistant."

    def _is_local_ollama(self) -> bool:
        hostname = urlparse(self.config.base_url or "http://localhost:11434").hostname
        return hostname in {"localhost", "127.0.0.1", "::1"}

    def _get_headers(self) -> Dict[str, str]:
        if self._is_local_ollama() or not self.config.api_key:
            return {}
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _get_sync_client(self) -> ollama.Client:
        if self._sync_client is None:
            headers = self._get_headers()
            if headers:
                self._sync_client = ollama.Client(host=self.config.base_url, headers=headers)
            else:
                self._sync_client = ollama.Client(host=self.config.base_url)
        return self._sync_client

    def _get_async_client(self) -> ollama.AsyncClient:
        if self._async_client is None:
            headers = self._get_headers()
            if headers:
                self._async_client = ollama.AsyncClient(host=self.config.base_url, headers=headers)
            else:
                self._async_client = ollama.AsyncClient(host=self.config.base_url)
        return self._async_client

    def _build_messages(self, prompt: str) -> list:
        return [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]

    def _generation_options(
        self,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        """Build Ollama generation options."""
        # Use config extra for defaults if provided
        extra = self.config.extra or {}
        limit = num_predict if num_predict is not None else extra.get("num_predict", 768)
        return {
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": extra.get("num_ctx", 4096),
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

    def _extract_ollama_metrics(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Ollama timing metrics from a non-streaming response."""
        return {
            "ttft_ms": 0.0,
            "total_ms": 0.0,
            "prompt_eval_count": response.get("prompt_eval_count", 0),
            "prompt_eval_duration_ms": (response.get("prompt_eval_duration", 0) / 1e6),
            "eval_count": response.get("eval_count", 0),
            "eval_duration_ms": (response.get("eval_duration", 0) / 1e6),
        }

    @property
    def provider_name(self) -> str:
        return "ollama"

    def generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response via Ollama."""
        client = self._get_sync_client()
        options = self._generation_options(num_predict, temperature, top_p)
        keep_alive = self.config.extra.get("keep_alive", "10m") if self.config.extra else "10m"

        try:
            self._log_safe(logging.INFO, "Ollama generate request", model=self.config.model)
            response = client.chat(
                model=self.config.model,
                messages=self._build_messages(prompt),
                stream=False,
                options=options,
                keep_alive=keep_alive,
            )
            message = response.get("message", {})
            text = message.get("content", "").strip()
            if not text:
                raise ProviderError(
                    kind="empty_response",
                    user_message="Ollama returned an empty response.",
                    status_code=502,
                )
            return text
        except ollama.ResponseError as exc:
            status = getattr(exc, "status_code", 500)
            if status == 401:
                raise ProviderError("auth_error", "Invalid Ollama API key.", 401) from exc
            if status == 402:
                raise ProviderError("payment_required", "Ollama model requires a subscription.", 402) from exc
            if status == 404:
                raise ProviderError("not_found", f"Ollama model '{self.config.model}' is not available.", 404) from exc
            raise ProviderError("server_error", f"Ollama API error: {status}", status) from exc
        except ollama.RequestError as exc:
            raise self._classify_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise self._classify_error(exc) from exc

    def stream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> Generator[str, None, None]:
        """Generate a streaming response via Ollama."""
        client = self._get_sync_client()
        options = self._generation_options(num_predict, temperature, top_p)
        keep_alive = self.config.extra.get("keep_alive", "10m") if self.config.extra else "10m"

        try:
            self._log_safe(logging.INFO, "Ollama stream request", model=self.config.model)
            t_first = None
            first_token_time = None
            for response in client.chat(
                model=self.config.model,
                messages=self._build_messages(prompt),
                stream=True,
                options=options,
                keep_alive=keep_alive,
            ):
                message = response.get("message", {})
                content = message.get("content", "")
                if content:
                    if t_first is None:
                        t_first = time.perf_counter()
                        first_token_time = t_first
                    yield content
                if response.get("done"):
                    break
        except ollama.ResponseError as exc:
            status = getattr(exc, "status_code", 500)
            if status == 401:
                raise ProviderError("auth_error", "Invalid Ollama API key.", 401) from exc
            if status == 402:
                raise ProviderError("payment_required", "Ollama model requires a subscription.", 402) from exc
            if status == 404:
                raise ProviderError("not_found", f"Ollama model '{self.config.model}' is not available.", 404) from exc
            raise ProviderError("server_error", f"Ollama API error: {status}", status) from exc
        except ollama.RequestError as exc:
            raise self._classify_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise self._classify_error(exc) from exc

    async def agenerate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response via Ollama (async)."""
        client = self._get_async_client()
        options = self._generation_options(num_predict, temperature, top_p)
        keep_alive = self.config.extra.get("keep_alive", "10m") if self.config.extra else "10m"

        try:
            self._log_safe(logging.INFO, "Ollama agenerate request", model=self.config.model)
            response = await client.chat(
                model=self.config.model,
                messages=self._build_messages(prompt),
                stream=False,
                options=options,
                keep_alive=keep_alive,
            )
            message = response.get("message", {})
            text = message.get("content", "").strip()
            if not text:
                raise ProviderError(
                    kind="empty_response",
                    user_message="Ollama returned an empty response.",
                    status_code=502,
                )
            return text
        except ollama.ResponseError as exc:
            status = getattr(exc, "status_code", 500)
            if status == 401:
                raise ProviderError("auth_error", "Invalid Ollama API key.", 401) from exc
            if status == 402:
                raise ProviderError("payment_required", "Ollama model requires a subscription.", 402) from exc
            if status == 404:
                raise ProviderError("not_found", f"Ollama model '{self.config.model}' is not available.", 404) from exc
            raise ProviderError("server_error", f"Ollama API error: {status}", status) from exc
        except ollama.RequestError as exc:
            raise self._classify_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise self._classify_error(exc) from exc

    async def astream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Generate a streaming response via Ollama (async)."""
        client = self._get_async_client()
        options = self._generation_options(num_predict, temperature, top_p)
        keep_alive = self.config.extra.get("keep_alive", "10m") if self.config.extra else "10m"

        try:
            self._log_safe(logging.INFO, "Ollama astream request", model=self.config.model)
            async for response in await client.chat(
                model=self.config.model,
                messages=self._build_messages(prompt),
                stream=True,
                options=options,
                keep_alive=keep_alive,
            ):
                message = response.get("message", {})
                content = message.get("content", "")
                if content:
                    yield content
                if response.get("done"):
                    break
        except ollama.ResponseError as exc:
            status = getattr(exc, "status_code", 500)
            if status == 401:
                raise ProviderError("auth_error", "Invalid Ollama API key.", 401) from exc
            if status == 402:
                raise ProviderError("payment_required", "Ollama model requires a subscription.", 402) from exc
            if status == 404:
                raise ProviderError("not_found", f"Ollama model '{self.config.model}' is not available.", 404) from exc
            raise ProviderError("server_error", f"Ollama API error: {status}", status) from exc
        except ollama.RequestError as exc:
            raise self._classify_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise self._classify_error(exc) from exc