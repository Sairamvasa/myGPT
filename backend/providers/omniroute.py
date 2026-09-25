"""OmniRoute provider implementation."""

import json
import logging
from typing import Optional, Generator, AsyncGenerator, Dict, Any

import httpx

from providers.base import LLMProvider, ProviderConfig, ProviderError

logger = logging.getLogger("MyGPT.Providers.OmniRoute")


class OmniRouteProvider(LLMProvider):
    """OmniRoute provider for centralized model routing."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        return "omniroute"

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            self._client = httpx.Client(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            self._async_client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._async_client

    def _build_request(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Build the request payload for OmniRoute."""
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
        }
        if num_predict is not None:
            payload["max_tokens"] = num_predict
        if self.config.extra:
            payload.update(self.config.extra)
        return payload

    def _parse_response(self, response: httpx.Response) -> str:
        """Parse non-streaming response."""
        data = response.json()
        # Handle OpenAI-compatible format
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
            if "text" in choice:
                return choice["text"]
        # Handle simple text response
        if "text" in data:
            return data["text"]
        if "content" in data:
            return data["content"]
        raise ProviderError(
            kind="malformed_response",
            user_message="Received malformed response from OmniRoute.",
            status_code=502,
        )

    @staticmethod
    def _parse_sse_events(buffer: str) -> tuple[list[str], str]:
        """Return complete SSE data events and retain an incomplete line."""
        lines = buffer.splitlines(keepends=True)
        remainder = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            remainder = lines.pop()

        events = []
        event_data = []
        for line in lines:
            line = line.rstrip("\r\n")
            if not line:
                if event_data:
                    events.append("\n".join(event_data))
                    event_data = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                value = line[5:]
                event_data.append(value[1:] if value.startswith(" ") else value)

        return events, remainder

    @staticmethod
    def _content_from_sse_data(data_text: str) -> Optional[str]:
        if data_text == "[DONE]":
            return None
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            return None
        choices = data.get("choices") or []
        if not choices:
            return None
        content = (choices[0].get("delta") or {}).get("content")
        return content if content else None

    def _iter_sse_content(self, chunks):
        buffer = ""
        for chunk in chunks:
            if not chunk:
                continue
            buffer += chunk.decode("utf-8")
            events, buffer = self._parse_sse_events(buffer)
            for data_text in events:
                if data_text == "[DONE]":
                    return
                content = self._content_from_sse_data(data_text)
                if content:
                    yield content

        if buffer:
            events, _ = self._parse_sse_events(buffer + "\n")
            for data_text in events:
                if data_text == "[DONE]":
                    return
                content = self._content_from_sse_data(data_text)
                if content:
                    yield content

    def generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """Generate a non-streaming response via OmniRoute."""
        client = self._get_client()
        payload = self._build_request(
            prompt, num_predict, temperature, top_p, stream=False, **kwargs
        )

        try:
            self._log_safe(logging.INFO, "OmniRoute generate request", model=self.config.model)
            response = client.post("/chat/completions", json=payload)
            response.raise_for_status()
            return self._parse_response(response)
        except httpx.HTTPStatusError as exc:
            raise self._classify_error(exc) from exc
        except httpx.RequestError as exc:
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
        """Generate a streaming response via OmniRoute."""
        client = self._get_client()
        payload = self._build_request(
            prompt, num_predict, temperature, top_p, stream=True, **kwargs
        )

        try:
            self._log_safe(logging.INFO, "OmniRoute stream request", model=self.config.model)
            with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                yield from self._iter_sse_content(response.iter_bytes())
        except httpx.HTTPStatusError as exc:
            raise self._classify_error(exc) from exc
        except httpx.RequestError as exc:
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
        """Generate a non-streaming response via OmniRoute (async)."""
        client = self._get_async_client()
        payload = self._build_request(
            prompt, num_predict, temperature, top_p, stream=False, **kwargs
        )

        try:
            self._log_safe(logging.INFO, "OmniRoute agenerate request", model=self.config.model)
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            return self._parse_response(response)
        except httpx.HTTPStatusError as exc:
            raise self._classify_error(exc) from exc
        except httpx.RequestError as exc:
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
        """Generate a streaming response via OmniRoute (async)."""
        client = self._get_async_client()
        payload = self._build_request(
            prompt, num_predict, temperature, top_p, stream=True, **kwargs
        )

        try:
            self._log_safe(logging.INFO, "OmniRoute astream request", model=self.config.model)
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async def chunks():
                    async for chunk in response.aiter_bytes():
                        yield chunk

                buffer = ""
                async for chunk in chunks():
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8")
                    events, buffer = self._parse_sse_events(buffer)
                    for data_text in events:
                        if data_text == "[DONE]":
                            return
                        content = self._content_from_sse_data(data_text)
                        if content:
                            yield content
                if buffer:
                    events, _ = self._parse_sse_events(buffer + "\n")
                    for data_text in events:
                        if data_text == "[DONE]":
                            return
                        content = self._content_from_sse_data(data_text)
                        if content:
                            yield content
        except httpx.HTTPStatusError as exc:
            raise self._classify_error(exc) from exc
        except httpx.RequestError as exc:
            raise self._classify_error(exc) from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise self._classify_error(exc) from exc

    def close(self):
        """Close HTTP clients."""
        if self._client:
            self._client.close()
            self._client = None
        if self._async_client:
            # Note: async close should be awaited, but we can't here
            self._async_client = None

    async def aclose(self):
        """Close async HTTP client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._client:
            self._client.close()
            self._client = None