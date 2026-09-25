import asyncio
import logging
import os

import httpx
import pytest

from providers.base import ProviderConfig, ProviderError
from providers.omniroute import OmniRouteProvider
from providers.registry import ProviderRegistry, configure_providers_from_env


class DummyProvider:
    def __init__(self, name, chunks=None, error=None):
        self._name = name
        self.chunks = chunks or []
        self.error = error

    @property
    def provider_name(self):
        return self._name

    def generate(self, *args, **kwargs):
        if self.error:
            raise self.error
        return "response"

    def stream_generate(self, *args, **kwargs):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error

    async def agenerate(self, *args, **kwargs):
        return self.generate(*args, **kwargs)

    async def astream_generate(self, *args, **kwargs):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


class FakeResponse:
    def __init__(self, payload=None, chunks=None, error=None):
        self.payload = payload
        self.chunks = chunks or []
        self.error = error

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.error:
            raise self.error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_bytes(self):
        yield from self.chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk


class FakeClient:
    def __init__(self, response):
        self.response = response

    def post(self, *args, **kwargs):
        return self.response

    def stream(self, *args, **kwargs):
        return self.response


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def post(self, *args, **kwargs):
        return self.response

    def stream(self, *args, **kwargs):
        return self.response


def make_provider():
    return OmniRouteProvider(ProviderConfig(
        name="omniroute",
        model="auto/test",
        api_key="test-secret-key",
        base_url="https://omniroute.test",
    ))


def test_omniroute_non_stream_response():
    provider = make_provider()
    provider._client = FakeClient(FakeResponse({"choices": [{"message": {"content": "hello"}}]}))
    assert provider.generate("hi") == "hello"


def test_omniroute_stream_response():
    provider = make_provider()
    chunks = [b'data: {"choices":[{"delta":{"content":"hel"}}]}\n\n', b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n']
    provider._client = FakeClient(FakeResponse(chunks=chunks))
    assert "".join(provider.stream_generate("hi")) == "hello"


def test_omniroute_sse_event_split_across_byte_chunks():
    provider = make_provider()
    provider._client = FakeClient(FakeResponse(chunks=[
        b'data: {"choices":[{"delta":{"con',
        b'tent":"hello"}}]}\n\n',
    ]))
    assert list(provider.stream_generate("hi")) == ["hello"]


def test_omniroute_done_event():
    provider = make_provider()
    provider._client = FakeClient(FakeResponse(chunks=[
        b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n',
        b'data: [DONE]\n\n',
        b'data: {"choices":[{"delta":{"content":"ignored"}}]}\n\n',
    ]))
    assert list(provider.stream_generate("hi")) == ["a"]


def test_omniroute_http_error():
    provider = make_provider()
    error = httpx.HTTPStatusError("server error", request=httpx.Request("POST", "https://omniroute.test"), response=httpx.Response(500))
    provider._client = FakeClient(FakeResponse(error=error))
    with pytest.raises(ProviderError) as caught:
        provider.generate("hi")
    assert caught.value.kind == "server_error"


def test_omniroute_timeout():
    provider = make_provider()
    provider._client = FakeClient(FakeResponse(error=httpx.ReadTimeout("timed out")))
    with pytest.raises(ProviderError) as caught:
        provider.generate("hi")
    assert caught.value.kind == "timeout"


def test_primary_provider_fallback():
    registry = ProviderRegistry()
    registry.register("primary", DummyProvider("primary", error=ProviderError("down", "down")), is_primary=True)
    registry.register("fallback", DummyProvider("fallback"), is_fallback=True)
    assert registry.execute_with_fallback("generate", "hi") == "response"


def test_streaming_provider_fallback_without_duplicate_prefix():
    registry = ProviderRegistry()
    registry.register("primary", DummyProvider("primary", chunks=["one"], error=ProviderError("down", "down")), is_primary=True)
    registry.register("fallback", DummyProvider("fallback", chunks=["one", " two"]), is_fallback=True)
    assert list(registry.execute_with_fallback("stream_generate", "hi")) == ["one", " two"]


def test_missing_omniroute_configuration(monkeypatch):
    for name in ("OMNIROUTE_BASE_URL", "OMNIROUTE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    registry = configure_providers_from_env()
    assert registry.get("omniroute") is None


def test_secrets_not_in_provider_errors_or_logs(caplog):
    secret = "test-secret-key"
    provider = OmniRouteProvider(ProviderConfig(name="omniroute", model="test", api_key=secret, base_url="https://test"))
    with caplog.at_level(logging.INFO):
        error = provider._classify_error(RuntimeError(f"Authorization: Bearer {secret}"))
    assert secret not in str(error)
    assert secret not in caplog.text


def test_async_omniroute_streaming_and_fallback():
    async def run():
        provider = make_provider()
        provider._async_client = FakeAsyncClient(FakeResponse(chunks=[
            b'data: {"choices":[{"delta":{"content":"async"}}]}\n\n', b'data: [DONE]\n\n'
        ]))
        assert [chunk async for chunk in provider.astream_generate("hi")] == ["async"]

        registry = ProviderRegistry()
        registry.register("primary", DummyProvider("primary", chunks=["a"], error=ProviderError("down", "down")), is_primary=True)
        registry.register("fallback", DummyProvider("fallback", chunks=["a", "b"]), is_fallback=True)
        stream = await registry.aexecute_with_fallback("astream_generate", "hi")
        assert [chunk async for chunk in stream] == ["a", "b"]

    asyncio.run(run())
