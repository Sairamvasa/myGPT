"""NVIDIA NIM provider for MyGPT."""

import os
import json
import logging
from typing import Optional, Generator, AsyncGenerator, Dict, Any

import httpx

from providers.base import (
    LLMProvider,
    ProviderConfig,
    ProviderError,
)

logger = logging.getLogger("MyGPT.Providers.NVIDIA")


class NvidiaProvider(LLMProvider):
    """NVIDIA NIM provider using OpenAI-compatible chat completions."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

        extra = config.extra or {}

        self.text_model = extra.get(
            "text_model",
            config.model,
        )

        self.vision_model = extra.get(
            "vision_model",
            os.getenv(
                "NVIDIA_VISION_MODEL",
                "deepseek-ai/deepseek-v4.1-flash",
            ),
        )

    @property
    def provider_name(self) -> str:
        return "nvidia"

    # ------------------------------------------------------------------
    # HTTP clients
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:

            if not self.config.api_key:
                raise ProviderError(
                    kind="auth_error",
                    user_message="NVIDIA API key is not configured.",
                    status_code=401,
                )

            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            self._client = httpx.Client(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )

        return self._client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:

            if not self.config.api_key:
                raise ProviderError(
                    kind="auth_error",
                    user_message="NVIDIA API key is not configured.",
                    status_code=401,
                )

            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            self._async_client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(self.config.timeout),
            )

        return self._async_client

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        prompt: str,
        **kwargs,
    ):
        messages = kwargs.get("messages")

        if messages is not None:
            return messages

        messages = []

        system_prompt = kwargs.get("system_prompt")

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        return messages

    def _build_request(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:

        vision = bool(
            kwargs.get("vision", False)
        )

        model = (
            self.vision_model
            if vision
            else kwargs.get(
                "model",
                self.text_model,
            )
        )

        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(
                prompt,
                **kwargs,
            ),
            "temperature": temperature,
            "top_p": top_p,
            "stream": stream,
        }

        if num_predict is not None:
            payload["max_tokens"] = num_predict

        # Optional NVIDIA-compatible arguments.
        for key in (
            "seed",
            "frequency_penalty",
            "presence_penalty",
        ):
            if (
                key in kwargs
                and kwargs[key] is not None
            ):
                payload[key] = kwargs[key]

        # Only pass reasoning_effort when explicitly supplied.
        # Do NOT automatically send the .env value yet.
        if kwargs.get("reasoning_effort") is not None:
            payload["reasoning_effort"] = kwargs[
                "reasoning_effort"
            ]

        # Additional provider configuration.
        if self.config.extra:
            for key, value in self.config.extra.items():

                if key in (
                    "text_model",
                    "vision_model",
                ):
                    continue

                payload.setdefault(key, value)

        return payload

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(
        response: httpx.Response,
    ) -> str:

        data = response.json()

        choices = data.get("choices")

        if not choices:
            raise ProviderError(
                kind="malformed_response",
                user_message="NVIDIA returned no choices.",
                status_code=502,
            )

        choice = choices[0]

        message = choice.get("message") or {}

        content = message.get("content")

        if isinstance(content, str):
            return content

        if isinstance(content, list):

            parts = []

            for item in content:

                if isinstance(item, dict):

                    text = item.get("text")

                    if text:
                        parts.append(
                            str(text)
                        )

            return "".join(parts)

        text = choice.get("text")

        if text is not None:
            return str(text)

        raise ProviderError(
            kind="malformed_response",
            user_message="NVIDIA returned a malformed response.",
            status_code=502,
        )

    @staticmethod
    def _parse_sse_line(
        line: str,
    ) -> Optional[str]:

        line = line.strip()

        if not line:
            return None

        if line.startswith("data:"):
            line = line[5:].strip()

        if (
            not line
            or line == "[DONE]"
        ):
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None

        choices = data.get("choices")

        if not choices:
            return None

        delta = (
            choices[0].get("delta")
            or {}
        )

        content = delta.get("content")

        if content:
            return str(content)

        return None

    # ------------------------------------------------------------------
    # Required abstract method: generate
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        **kwargs,
    ) -> str:

        client = self._get_client()

        payload = self._build_request(
            prompt,
            num_predict,
            temperature,
            top_p,
            stream=False,
            **kwargs,
        )

        try:

            self._log_safe(
                logging.INFO,
                "NVIDIA generate request",
                model=payload.get("model"),
            )

            response = client.post(
                "/chat/completions",
                json=payload,
            )

            response.raise_for_status()

            result = self._parse_response(
                response
            ).strip()

            if not result:
                raise ProviderError(
                    kind="empty_response",
                    user_message="NVIDIA returned an empty response.",
                    status_code=502,
                )

            return result

        except ProviderError:
            raise

        except httpx.HTTPStatusError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except httpx.RequestError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except Exception as exc:
            raise self._classify_error(
                exc
            ) from exc

    # ------------------------------------------------------------------
    # Required abstract method: stream_generate
    # ------------------------------------------------------------------

    def stream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        **kwargs,
    ) -> Generator[str, None, None]:

        client = self._get_client()

        payload = self._build_request(
            prompt,
            num_predict,
            temperature,
            top_p,
            stream=True,
            **kwargs,
        )

        try:

            self._log_safe(
                logging.INFO,
                "NVIDIA stream request",
                model=payload.get("model"),
            )

            with client.stream(
                "POST",
                "/chat/completions",
                json=payload,
            ) as response:

                response.raise_for_status()

                for line in response.iter_lines():

                    content = (
                        self._parse_sse_line(
                            line
                        )
                    )

                    if content:
                        yield content

        except ProviderError:
            raise

        except httpx.HTTPStatusError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except httpx.RequestError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except Exception as exc:
            raise self._classify_error(
                exc
            ) from exc

    # ------------------------------------------------------------------
    # Required abstract method: agenerate
    # ------------------------------------------------------------------

    async def agenerate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        **kwargs,
    ) -> str:

        client = self._get_async_client()

        payload = self._build_request(
            prompt,
            num_predict,
            temperature,
            top_p,
            stream=False,
            **kwargs,
        )

        try:

            self._log_safe(
                logging.INFO,
                "NVIDIA async generate request",
                model=payload.get("model"),
            )

            response = await client.post(
                "/chat/completions",
                json=payload,
            )

            response.raise_for_status()

            result = self._parse_response(
                response
            ).strip()

            if not result:
                raise ProviderError(
                    kind="empty_response",
                    user_message="NVIDIA returned an empty response.",
                    status_code=502,
                )

            return result

        except ProviderError:
            raise

        except httpx.HTTPStatusError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except httpx.RequestError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except Exception as exc:
            raise self._classify_error(
                exc
            ) from exc

    # ------------------------------------------------------------------
    # Required abstract method: astream_generate
    # ------------------------------------------------------------------

    async def astream_generate(
        self,
        prompt: str,
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
        **kwargs,
    ) -> AsyncGenerator[str, None]:

        client = self._get_async_client()

        payload = self._build_request(
            prompt,
            num_predict,
            temperature,
            top_p,
            stream=True,
            **kwargs,
        )

        try:

            self._log_safe(
                logging.INFO,
                "NVIDIA async stream request",
                model=payload.get("model"),
            )

            async with client.stream(
                "POST",
                "/chat/completions",
                json=payload,
            ) as response:

                response.raise_for_status()

                async for line in response.aiter_lines():

                    content = (
                        self._parse_sse_line(
                            line
                        )
                    )

                    if content:
                        yield content

        except ProviderError:
            raise

        except httpx.HTTPStatusError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except httpx.RequestError as exc:
            raise self._classify_error(
                exc
            ) from exc

        except Exception as exc:
            raise self._classify_error(
                exc
            ) from exc

    # ------------------------------------------------------------------
    # Vision helper
    # ------------------------------------------------------------------

    def generate_with_image(
        self,
        prompt: str,
        image_base64: str,
        image_mime_type: str = "image/jpeg",
        num_predict: Optional[int] = None,
        temperature: float = 1.0,
        top_p: float = 0.95,
    ) -> str:
        """Generate a response from text + image."""

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
                                f"data:{image_mime_type};base64,"
                                f"{image_base64}"
                            )
                        },
                    },
                ],
            }
        ]

        return self.generate(
            "",
            num_predict=num_predict,
            temperature=temperature,
            top_p=top_p,
            model=self.vision_model,
            vision=True,
            messages=messages,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

        self._async_client = None

    async def aclose(self):
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

        if self._client:
            self._client.close()
            self._client = None
