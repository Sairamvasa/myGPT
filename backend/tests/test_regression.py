import os
import pytest
from unittest.mock import patch, MagicMock

# Set up environment before importing backend code
os.environ["JWT_SECRET_KEY"] = "dummy"

from providers.registry import configure_providers_from_env, get_registry
from providers.base import ProviderError
from llm import stream_llm_routed, LLMError

@pytest.fixture
def mock_env():
    env_vars = {
        "APP_ENV": "production",
        "AI_PROVIDER": "gemini",
        "GEMINI_API_KEY": "fake_gemini_key",
        "OLLAMA_BASE_URL": "http://localhost:11434",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        yield

def test_production_ai_provider_gemini(mock_env):
    """Test that in production with AI_PROVIDER=gemini, Gemini is primary and local Ollama is disabled."""
    registry = configure_providers_from_env()
    assert registry._primary_provider == "gemini"
    assert "ollama" not in registry._providers

def test_production_must_not_silently_select_local_ollama(mock_env):
    """Test that production environment refuses to use local Ollama even if configured as primary."""
    with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
        registry = configure_providers_from_env()
        # Should switch to Gemini because Ollama is local and it's production
        assert registry._primary_provider == "gemini"
        assert "ollama" not in registry._providers

def test_provider_alias_precedence(mock_env):
    """Test MODEL_ROUTER_PROVIDER over PROVIDER_PRIMARY over LLM_PROVIDER over AI_PROVIDER."""
    # Test MODEL_ROUTER_PROVIDER overrides
    with patch.dict(os.environ, {
        "AI_PROVIDER": "gemini",
        "LLM_PROVIDER": "omniroute",
        "MODEL_ROUTER_PROVIDER": "omniroute",
        "OMNIROUTE_API_KEY": "omni_key",
        "OMNIROUTE_BASE_URL": "http://omni",
    }):
        registry = configure_providers_from_env()
        assert registry._primary_provider == "omniroute"

def test_missing_gemini_api_key(mock_env):
    """Test behavior when Gemini API key is missing but Gemini is requested in production."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "AI_PROVIDER": "gemini"}):
        with pytest.raises(RuntimeError, match="No cloud LLM provider is configured for production"):
            configure_providers_from_env()

@patch("google.genai.Client")
def test_gemini_provider_initialization(mock_client, mock_env):
    """Test GeminiProvider initializes with correct config."""
    registry = configure_providers_from_env()
    gemini_provider = registry._providers["gemini"]

    assert gemini_provider.config.api_key == "fake_gemini_key"
    client = gemini_provider._get_client()
    mock_client.assert_called_once_with(api_key="fake_gemini_key")

@patch("providers.gemini.GeminiProvider.stream_generate")
def test_stream_provider_failure(mock_stream_generate, mock_env):
    """Test that if Gemini stream fails, the registry raises a ProviderError that routes correctly."""
    mock_stream_generate.side_effect = ProviderError("server_error", "Mock error", 500)

    registry = configure_providers_from_env()

    with pytest.raises(LLMError) as exc_info:
        list(stream_llm_routed("hello", "chat"))

    assert exc_info.value.kind == "all_providers_failed"

@patch("providers.gemini.GeminiProvider.stream_generate")
def test_stream_successful_gemini_response(mock_stream_generate, mock_env):
    """Test that a successful Gemini response yields chunks."""
    mock_stream_generate.return_value = ["Hello", " world"]

    registry = configure_providers_from_env()
    chunks = list(stream_llm_routed("hello", "chat"))

    assert chunks == ["Hello", " world"]
