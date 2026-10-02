"""Multi-provider LLM registry for MyGPT.

Supports NVIDIA, Gemini, OmniRoute (cloud providers) and Ollama (local-only in
production).  Provider selection follows alias precedence:

    MODEL_ROUTER_PROVIDER > PROVIDER_PRIMARY > LLM_PROVIDER > AI_PROVIDER
"""

import os
import logging
from typing import Optional, Dict, List, Any, Generator, AsyncGenerator
from urllib.parse import urlparse

from providers.base import LLMProvider, ProviderConfig, ProviderError
from providers.nvidia import NvidiaProvider
from providers.gemini import GeminiProvider
from providers.omniroute import OmniRouteProvider
from providers.ollama import OllamaProvider

logger = logging.getLogger("MyGPT.ProviderRegistry")

# ---------------------------------------------------------------------------
# Provider classification
# ---------------------------------------------------------------------------

CLOUD_PROVIDERS = frozenset({"nvidia", "gemini", "omniroute"})
LOCAL_PROVIDERS = frozenset({"ollama"})
KNOWN_PROVIDERS = CLOUD_PROVIDERS | LOCAL_PROVIDERS

_STREAMING_METHODS = frozenset({"stream_generate", "astream_generate"})


# ---------------------------------------------------------------------------
# Per-provider config builders
# ---------------------------------------------------------------------------

def _build_nvidia_config() -> ProviderConfig:
    api_key = os.getenv("NVIDIA_API_KEY", "")
    base_url = os.getenv(
        "NVIDIA_BASE_URL",
        "https://integrate.api.nvidia.com/v1",
    ).rstrip("/")
    text_model = os.getenv("NVIDIA_TEXT_MODEL", "deepseek-ai/deepseek-v4-flash")
    vision_model = os.getenv("NVIDIA_VISION_MODEL", "deepseek-ai/deepseek-v4.1-flash")
    timeout = float(os.getenv("NVIDIA_TIMEOUT", "60"))
    return ProviderConfig(
        name="nvidia",
        model=text_model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        extra={"text_model": text_model, "vision_model": vision_model},
    )


def _build_gemini_config() -> ProviderConfig:
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    timeout = float(os.getenv("GEMINI_TIMEOUT", "60"))
    return ProviderConfig(
        name="gemini",
        model=model,
        api_key=api_key,
        base_url=None,
        timeout=timeout,
        extra={"max_retries": 2, "base_delay": 1.0, "max_delay": 8.0},
    )


def _build_omniroute_config() -> ProviderConfig:
    api_key = os.getenv("OMNIROUTE_API_KEY", "")
    base_url = os.getenv(
        "OMNIROUTE_BASE_URL",
        "http://localhost:8000",
    ).rstrip("/")
    model = os.getenv("OMNIROUTE_MODEL", "gpt-4")
    timeout = float(os.getenv("OMNIROUTE_TIMEOUT", "60"))
    return ProviderConfig(
        name="omniroute",
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )


def _build_ollama_config() -> ProviderConfig:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    timeout = float(os.getenv("OLLAMA_TIMEOUT", "60"))
    return ProviderConfig(
        name="ollama",
        model=model,
        api_key=None,
        base_url=base_url,
        timeout=timeout,
        extra={"num_ctx": 4096, "keep_alive": "10m"},
    )


_PROVIDER_BUILDERS: Dict[str, Any] = {
    "nvidia": _build_nvidia_config,
    "gemini": _build_gemini_config,
    "omniroute": _build_omniroute_config,
    "ollama": _build_ollama_config,
}

_PROVIDER_CLASSES: Dict[str, Any] = {
    "nvidia": NvidiaProvider,
    "gemini": GeminiProvider,
    "omniroute": OmniRouteProvider,
    "ollama": OllamaProvider,
}


def _is_local_ollama(provider: LLMProvider) -> bool:
    """Return True when *provider* is an Ollama pointing at localhost."""

    if not isinstance(provider, OllamaProvider):
        return False
    hostname = urlparse(provider.config.base_url or "").hostname
    return hostname in {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Provider registry with fallback-chain support."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._primary_provider: Optional[str] = None
        self._fallback_chain: List[str] = []

    # -- mutation ----------------------------------------------------------

    def register(
        self,
        name: str,
        provider: LLMProvider,
        is_primary: bool = False,
        is_fallback: bool = False,
    ):
        """Register a provider."""

        self._providers[name] = provider

        if is_primary:
            self._primary_provider = name
            self._fallback_chain = [
                item for item in self._fallback_chain
                if item != name
            ]
        elif is_fallback and name not in self._fallback_chain:
            self._fallback_chain.append(name)

        logger.info(
            "Registered provider: %s (primary=%s, fallback=%s)",
            name,
            is_primary,
            is_fallback,
        )

    def unregister(self, name: str):
        """Remove a provider from the registry."""
        self._providers.pop(name, None)
        if self._primary_provider == name:
            self._primary_provider = None
        self._fallback_chain = [
            item for item in self._fallback_chain if item != name
        ]

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> Optional[LLMProvider]:
        """Get a provider by name."""

        return self._providers.get(name)

    def get_primary(self) -> Optional[LLMProvider]:
        """Get the primary provider."""

        if self._primary_provider:
            return self._providers.get(self._primary_provider)
        return None

    def get_fallback_chain(self) -> List[LLMProvider]:
        """Return fallback providers in order."""

        return [
            self._providers[name]
            for name in self._fallback_chain
            if name in self._providers
        ]

    # -- execution ---------------------------------------------------------

    def _providers_to_try(
        self,
        primary_only: bool = False,
    ) -> List[LLMProvider]:
        """Return the ordered list of providers to attempt."""

        result: List[LLMProvider] = []
        primary = self.get_primary()
        if primary is not None:
            result.append(primary)
        if not primary_only:
            for name in self._fallback_chain:
                provider = self._providers.get(name)
                if provider is not None and provider not in result:
                    result.append(provider)
        return result

    def _all_providers_failed_error(
        self,
        last_error: Optional[Exception],
    ) -> ProviderError:
        """Build the canonical 'all providers failed' error."""

        if last_error is None:
            return ProviderError(
                kind="all_providers_failed",
                user_message="No LLM provider is available.",
                status_code=503,
            )

        return ProviderError(
            kind="all_providers_failed",
            user_message=(
                f"All LLM providers failed. Last error: {last_error}"
            ),
            status_code=503,
            retry_after=getattr(last_error, "retry_after", None),
            original_exception=last_error,
        )

    def _make_provider_error(
        self,
        provider: LLMProvider,
        exc: Exception,
    ) -> ProviderError:
        """Normalise a raw exception into a ProviderError."""

        if isinstance(exc, ProviderError):
            return exc

        return ProviderError(
            kind="unknown_error",
            user_message=f"{provider.provider_name} failed to respond.",
            status_code=503,
            original_exception=exc,
        )

    def execute_with_fallback(
        self,
        method_name: str,
        *args: Any,
        primary_only: bool = False,
        **kwargs: Any,
    ):
        """Execute *method_name* on the primary provider, falling back.

        For streaming methods (``stream_generate`` / ``astream_generate``)
        a generator is returned so the caller can iterate lazily.
        """

        providers = self._providers_to_try(primary_only)

        if method_name in _STREAMING_METHODS:
            return self._stream_with_fallback(
                method_name, providers, args, kwargs
            )

        return self._call_with_fallback(
            method_name, providers, args, kwargs
        )

    def _call_with_fallback(
        self,
        method_name: str,
        providers: List[LLMProvider],
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Synchronous fallback for non-streaming methods."""

        last_error: Optional[ProviderError] = None

        for provider in providers:
            try:
                method = getattr(provider, method_name)
                result = method(*args, **kwargs)
                if result is not None:
                    return result
            except ProviderError as exc:
                last_error = exc
                logger.warning(
                    "Provider %s failed: %s",
                    provider.provider_name,
                    exc.kind,
                )
            except Exception as exc:
                last_error = self._make_provider_error(provider, exc)
                logger.exception(
                    "Provider %s raised %s",
                    provider.provider_name,
                    type(exc).__name__,
                )

        raise self._all_providers_failed_error(last_error)

    def _stream_with_fallback(
        self,
        method_name: str,
        providers: List[LLMProvider],
        args: tuple,
        kwargs: dict,
    ) -> Generator[str, None, None]:
        """Streaming fallback — tries each provider in sequence."""

        last_error: Optional[ProviderError] = None

        for provider in providers:
            try:
                method = getattr(provider, method_name)
                stream = method(*args, **kwargs)

                emitted = False
                for chunk in stream:
                    if chunk:
                        emitted = True
                        yield chunk

                if emitted:
                    return
                logger.warning(
                    "Provider %s produced an empty stream.",
                    provider.provider_name,
                )
            except ProviderError as exc:
                last_error = exc
                logger.warning(
                    "Provider %s stream failed: %s",
                    provider.provider_name,
                    exc.kind,
                )
            except Exception as exc:
                last_error = self._make_provider_error(provider, exc)
                logger.exception(
                    "Provider %s stream raised %s",
                    provider.provider_name,
                    type(exc).__name__,
                )

        raise self._all_providers_failed_error(last_error)

    async def aexecute_with_fallback(
        self,
        method_name: str,
        *args: Any,
        primary_only: bool = False,
        **kwargs: Any,
    ):
        """Async execution with fallback."""

        providers = self._providers_to_try(primary_only)

        if method_name == "astream_generate":
            async def _astream():
                last_error: Optional[ProviderError] = None
                for provider in providers:
                    try:
                        method = getattr(provider, method_name)
                        stream = method(*args, **kwargs)
                        result = await stream
                        emitted = False
                        async for chunk in result:
                            if chunk:
                                emitted = True
                                yield chunk
                        if emitted:
                            return
                    except ProviderError as exc:
                        last_error = exc
                    except Exception as exc:
                        last_error = self._make_provider_error(provider, exc)
                raise self._all_providers_failed_error(last_error)
            return _astream()

        last_error = None
        for provider in providers:
            try:
                method = getattr(provider, method_name)
                result = await method(*args, **kwargs)
                if result is not None:
                    return result
            except ProviderError as exc:
                last_error = exc
            except Exception as exc:
                last_error = self._make_provider_error(provider, exc)
        raise self._all_providers_failed_error(last_error)

    # -- cleanup -----------------------------------------------------------

    def close_all(self):
        """Close provider resources."""

        for provider in self._providers.values():
            if hasattr(provider, "close"):
                try:
                    provider.close()
                except Exception:
                    logger.exception(
                        "Failed to close provider %s",
                        provider.provider_name,
                    )

    async def aclose_all(self):
        """Close async provider resources."""

        for provider in self._providers.values():
            if hasattr(provider, "aclose"):
                try:
                    await provider.aclose()
                except Exception:
                    logger.exception(
                        "Failed to close async provider %s",
                        provider.provider_name,
                    )


# ---------------------------------------------------------------------------
# Global registry + configuration
# ---------------------------------------------------------------------------

_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Get or create the global provider registry."""

    global _registry

    if _registry is None:
        _registry = ProviderRegistry()

    return _registry


def configure_providers_from_env() -> ProviderRegistry:
    """Configure providers from environment variables.

    Alias precedence: MODEL_ROUTER_PROVIDER > PROVIDER_PRIMARY >
    LLM_PROVIDER > AI_PROVIDER.

    In production (APP_ENV=production) local Ollama providers are never
    registered — the function falls through to the next configured cloud
    provider.
    """

    global _registry

    registry = get_registry()

    # Clear any existing configuration.
    registry._providers.clear()
    registry._primary_provider = None
    registry._fallback_chain.clear()

    app_env = os.getenv("APP_ENV", "development")
    is_production = app_env == "production"

    # Walk aliases in precedence order to pick the primary.
    primary_name = None
    for env_var in (
        "MODEL_ROUTER_PROVIDER",
        "PROVIDER_PRIMARY",
        "LLM_PROVIDER",
        "AI_PROVIDER",
    ):
        value = os.getenv(env_var, "").strip().lower()

        if not value or value not in KNOWN_PROVIDERS:
            continue

        if value in LOCAL_PROVIDERS and is_production:
            logger.info(
                "%s requested via %s but production refuses local providers",
                value,
                env_var,
            )
            continue

        builder = _PROVIDER_BUILDERS.get(value)
        if builder is None:
            continue

        config = builder()

        # Cloud providers require an API key.
        if value in CLOUD_PROVIDERS and not config.api_key:
            logger.warning(
                "Provider %s requested but no API key is set", value,
            )
            continue

        provider_cls = _PROVIDER_CLASSES[value]
        provider = provider_cls(config)
        registry.register(value, provider, is_primary=True)
        primary_name = value
        break

    # Register fallback providers (other cloud providers with keys).
    if primary_name is not None and is_production:
        for env_var in (
            "MODEL_ROUTER_PROVIDER",
            "PROVIDER_PRIMARY",
            "LLM_PROVIDER",
            "AI_PROVIDER",
        ):
            value = os.getenv(env_var, "").strip().lower()

            if not value or value not in CLOUD_PROVIDERS:
                continue
            if value == primary_name:
                continue

            builder = _PROVIDER_BUILDERS.get(value)
            if builder is None:
                continue

            config = builder()
            if not config.api_key:
                continue

            provider_cls = _PROVIDER_CLASSES[value]
            provider = provider_cls(config)
            registry.register(value, provider, is_fallback=True)

    if primary_name is None:
        if is_production:
            raise RuntimeError(
                "No cloud LLM provider is configured for production."
            )

        # Development fallback: try a local provider.
        for env_var in (
            "MODEL_ROUTER_PROVIDER",
            "PROVIDER_PRIMARY",
            "LLM_PROVIDER",
            "AI_PROVIDER",
        ):
            value = os.getenv(env_var, "").strip().lower()
            if value in LOCAL_PROVIDERS:
                builder = _PROVIDER_BUILDERS.get(value)
                if builder is None:
                    continue
                config = builder()
                provider_cls = _PROVIDER_CLASSES[value]
                provider = provider_cls(config)
                registry.register(value, provider, is_primary=True)
                primary_name = value
                break

        if primary_name is None:
            raise RuntimeError(
                "No LLM provider is configured. "
                "Set AI_PROVIDER (or LLM_PROVIDER / MODEL_ROUTER_PROVIDER) "
                "and the corresponding API key."
            )

    logger.info(
        "Provider registry configured: primary=%s, fallbacks=%s",
        registry._primary_provider,
        registry._fallback_chain,
    )

    return registry


def get_routed_provider_metadata() -> tuple:
    """Return (provider_name, model) for the configured provider."""

    registry = get_registry()
    provider = registry.get_primary()

    if provider is None:
        return ("unknown", os.getenv("NVIDIA_TEXT_MODEL", "deepseek-ai/deepseek-v4-flash"))

    return (provider.provider_name, provider.config.model)


def reload_registry() -> ProviderRegistry:
    """Reload the provider configuration from environment."""

    global _registry

    if _registry is not None:
        _registry.close_all()

    _registry = ProviderRegistry()

    return configure_providers_from_env()


# Configure immediately when an API key is present at import time.
if os.getenv("NVIDIA_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OMNIROUTE_API_KEY"):
    try:
        configure_providers_from_env()
    except Exception as exc:
        logger.warning(
            "Provider registry was not configured during module import: %s",
            type(exc).__name__,
        )
