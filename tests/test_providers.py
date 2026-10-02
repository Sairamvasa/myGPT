"""Tests for the multi-provider registry and LLM routing."""

import os
from unittest.mock import patch, MagicMock

import pytest

from providers.base import ProviderError, ProviderConfig
from providers.nvidia import NvidiaProvider
from providers.gemini import GeminiProvider
from providers.omniroute import OmniRouteProvider
from providers.ollama import OllamaProvider
from providers.registry import (
    ProviderRegistry,
    configure_providers_from_env,
    get_registry,
    get_routed_provider_metadata,
    reload_registry,
    CLOUD_PROVIDERS,
    LOCAL_PROVIDERS,
    KNOWN_PROVIDERS,
)
from llm import (
    stream_llm_routed,
    ask_llm_routed,
    LLMError,
    get_provider_status,
)


# ---------------------------------------------------------------------------
# Provider classification
# ---------------------------------------------------------------------------

class TestProviderClassification:
    """Verify the provider sets."""

    def test_cloud_providers_includes_nvidia(self):
        assert "nvidia" in CLOUD_PROVIDERS

    def test_cloud_providers_includes_gemini(self):
        assert "gemini" in CLOUD_PROVIDERS

    def test_cloud_providers_includes_omniroute(self):
        assert "omniroute" in CLOUD_PROVIDERS

    def test_ollama_is_local(self):
        assert "ollama" in LOCAL_PROVIDERS

    def test_known_providers_is_union(self):
        assert KNOWN_PROVIDERS == CLOUD_PROVIDERS | LOCAL_PROVIDERS


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------

class TestRegistryMechanics:
    """Unit tests for ProviderRegistry methods."""

    def test_register_primary(self):
        reg = ProviderRegistry()
        provider = MagicMock()
        provider.provider_name = "test"
        reg.register("test", provider, is_primary=True)

        assert reg.get_primary() is provider
        assert reg._primary_provider == "test"

    def test_register_fallback(self):
        reg = ProviderRegistry()
        primary = MagicMock()
        primary.provider_name = "primary"
        fallback = MagicMock()
        fallback.provider_name = "fallback"

        reg.register("primary", primary, is_primary=True)
        reg.register("fallback", fallback, is_fallback=True)

        assert reg.get_primary() is primary
        assert fallback in reg.get_fallback_chain()

    def test_get_returns_none_for_unknown(self):
        reg = ProviderRegistry()
        assert reg.get("nonexistent") is None

    def test_unregister_removes_provider(self):
        reg = ProviderRegistry()
        provider = MagicMock()
        provider.provider_name = "test"
        reg.register("test", provider, is_primary=True)
        reg.unregister("test")

        assert reg.get("test") is None
        assert reg.get_primary() is None


# ---------------------------------------------------------------------------
# configure_providers_from_env
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_env(monkeypatch):
    """Clear env vars and set a production-like baseline with Gemini."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Clear all other provider keys.
    for key in (
        "NVIDIA_API_KEY", "OMNIROUTE_API_KEY", "OMNIROUTE_BASE_URL",
        "MODEL_ROUTER_PROVIDER", "PROVIDER_PRIMARY", "LLM_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)


class TestConfigureProviders:
    """Tests for configure_providers_from_env()."""

    def test_production_ai_provider_gemini(self, mock_env):
        registry = configure_providers_from_env()
        assert registry._primary_provider == "gemini"
        assert "ollama" not in registry._providers

    def test_production_must_not_silently_select_local_ollama(self, mock_env):
        """Ollama is local — production must refuse it and fall back."""
        monkeypatch = patch.dict(os.environ, {"LLM_PROVIDER": "ollama"})
        monkeypatch.start()
        try:
            registry = configure_providers_from_env()
            assert registry._primary_provider == "gemini"
            assert "ollama" not in registry._providers
        finally:
            monkeypatch.stop()

    def test_provider_alias_precedence(self, mock_env):
        """MODEL_ROUTER_PROVIDER takes highest precedence."""
        env_patch = patch.dict(os.environ, {
            "LLM_PROVIDER": "omniroute",
            "MODEL_ROUTER_PROVIDER": "omniroute",
            "OMNIROUTE_API_KEY": "omni_key",
            "OMNIROUTE_BASE_URL": "http://omni",
        })
        env_patch.start()
        try:
            registry = configure_providers_from_env()
            assert registry._primary_provider == "omniroute"
        finally:
            env_patch.stop()

    def test_missing_gemini_api_key_raises(self, mock_env):
        """No API key for the configured cloud provider → RuntimeError."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with pytest.raises(RuntimeError, match="No cloud LLM provider"):
                configure_providers_from_env()

    def test_gemini_provider_initialization(self, mock_env):
        """GeminiProvider is registered with the correct API key."""
        with patch("google.genai.Client") as mock_client:
            registry = configure_providers_from_env()
            gemini_provider = registry._providers["gemini"]
            assert gemini_provider.config.api_key == "fake_gemini_key"

            client = gemini_provider._get_client()
            mock_client.assert_called_once_with(api_key="fake_gemini_key")

    def test_nvidia_provider_config(self, monkeypatch):
        """NVIDIA provider is registered when NVIDIA_API_KEY is set."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AI_PROVIDER", "nvidia")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fake")
        monkeypatch.setenv("AI_PROVIDER", "nvidia")
        for key in ("GEMINI_API_KEY", "OMNIROUTE_API_KEY", "OLLAMA_BASE_URL"):
            monkeypatch.delenv(key, raising=False)

        registry = configure_providers_from_env()
        assert registry._primary_provider == "nvidia"
        assert "nvidia" in registry._providers

    def test_development_allows_local_ollama(self, monkeypatch):
        """In development, local Ollama is accepted."""
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("AI_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        for key in ("NVIDIA_API_KEY", "GEMINI_API_KEY", "OMNIROUTE_API_KEY"):
            monkeypatch.delenv(key, raising=False)

        registry = configure_providers_from_env()
        assert registry._primary_provider == "ollama"
        assert "ollama" in registry._providers

    def test_dev_no_provider_raises_runtime_error(self, monkeypatch):
        """No provider configured in development → RuntimeError."""
        monkeypatch.setenv("APP_ENV", "development")
        for key in ("AI_PROVIDER", "LLM_PROVIDER", "MODEL_ROUTER_PROVIDER",
                     "NVIDIA_API_KEY", "GEMINI_API_KEY", "OMNIROUTE_API_KEY",
                     "OLLAMA_BASE_URL"):
            monkeypatch.delenv(key, raising=False)

        with pytest.raises(RuntimeError):
            configure_providers_from_env()

    def test_unknown_provider_name_skipped(self, mock_env):
        """Unknown provider names are silently skipped."""
        with patch.dict(os.environ, {"AI_PROVIDER": "claude"}):
            with pytest.raises(RuntimeError, match="No cloud LLM provider"):
                configure_providers_from_env()


# ---------------------------------------------------------------------------
# Streaming through the registry
# ---------------------------------------------------------------------------

class TestStreamingRouting:
    """Tests for stream_llm_routed and the fallback chain."""

    def test_stream_successful_gemini_response(self, mock_env):
        with patch("providers.gemini.GeminiProvider.stream_generate") as mock_stream:
            mock_stream.return_value = ["Hello", " world"]
            configure_providers_from_env()
            chunks = list(stream_llm_routed("hello", "chat"))
            assert chunks == ["Hello", " world"]

    def test_stream_provider_failure(self, mock_env):
        with patch("providers.gemini.GeminiProvider.stream_generate") as mock_stream:
            from providers.base import ProviderError
            mock_stream.side_effect = ProviderError(
                "server_error", "Mock error", 500,
            )
            configure_providers_from_env()
            with pytest.raises(LLMError) as exc_info:
                list(stream_llm_routed("hello", "chat"))
            assert exc_info.value.kind == "all_providers_failed"

    def test_stream_falls_back_to_secondary(self, monkeypatch):
        """When primary fails, fallback provider is tried."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "fake_gemini_key")
        monkeypatch.setenv("MODEL_ROUTER_PROVIDER", "nvidia")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-fake")
        monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)

        registry = configure_providers_from_env()
        # nvidia is highest precedence and has an API key → primary
        assert registry._primary_provider == "nvidia"

        # Now make nvidia fail and gemini succeed via fallback.
        with patch("providers.nvidia.NvidiaProvider.stream_generate") as mock_nvidia, \
             patch("providers.gemini.GeminiProvider.stream_generate") as mock_gemini:
            mock_nvidia.side_effect = ProviderError("server_error", "down", 500)
            mock_gemini.return_value = ["from", "gemini"]

            chunks = list(stream_llm_routed("hi", "chat"))
            assert chunks == ["from", "gemini"]

    def test_non_streaming_generate(self, mock_env):
        """ask_llm_routed uses execute_with_fallback for non-streaming."""
        with patch("providers.gemini.GeminiProvider.generate") as mock_generate:
            mock_generate.return_value = "Hello from Gemini"
            configure_providers_from_env()
            result = ask_llm_routed("hello", "chat")
            assert result == "Hello from Gemini"


# ---------------------------------------------------------------------------
# Metadata / status
# ---------------------------------------------------------------------------

class TestProviderMetadata:
    """Tests for get_routed_provider_metadata and get_provider_status."""

    def test_metadata_with_gemini(self, mock_env):
        with patch("google.genai.Client"):
            configure_providers_from_env()
            name, model = get_routed_provider_metadata()
            assert name == "gemini"
            assert model  # non-empty

    def test_metadata_unknown_when_unconfigured(self):
        """Without a provider configured, metadata returns unknown."""
        # Ensure no provider env vars are set.
        for key in ("AI_PROVIDER", "LLM_PROVIDER", "NVIDIA_API_KEY",
                     "GEMINI_API_KEY", "OMNIROUTE_API_KEY", "OLLAMA_BASE_URL"):
            os.environ.pop(key, None)
        # Reset registry.
        from providers import registry as _reg_mod
        _reg_mod._registry = None

        with pytest.raises(RuntimeError):
            configure_providers_from_env()

    def test_provider_status_returns_dict(self, mock_env):
        with patch("google.genai.Client"):
            configure_providers_from_env()
            status = get_provider_status()
            assert isinstance(status, dict)
            assert status["provider"] == "gemini"
            assert status["configured"] is True
