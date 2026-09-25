"""Provider factory and registry for managing LLM providers."""

import os
import logging
from typing import Optional, Dict, List, Any
from providers.base import LLMProvider, ProviderConfig, ProviderError
from providers.omniroute import OmniRouteProvider
from providers.ollama import OllamaProvider
from providers.gemini import GeminiProvider

logger = logging.getLogger("MyGPT.ProviderRegistry")


class ProviderRegistry:
    """Registry for managing LLM providers with fallback support."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._primary_provider: Optional[str] = None
        self._fallback_chain: List[str] = []

    def register(self, name: str, provider: LLMProvider, is_primary: bool = False, is_fallback: bool = False):
        """Register a provider."""
        self._providers[name] = provider
        if is_primary:
            self._primary_provider = name
            self._fallback_chain = [item for item in self._fallback_chain if item != name]
        elif is_fallback and name not in self._fallback_chain:
            self._fallback_chain.append(name)
        logger.info("Registered provider: %s (primary=%s, fallback=%s)", name, is_primary, is_fallback)

    def get(self, name: str) -> Optional[LLMProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_primary(self) -> Optional[LLMProvider]:
        """Get the primary provider."""
        if self._primary_provider:
            return self._providers.get(self._primary_provider)
        return None

    def get_fallback_chain(self) -> List[LLMProvider]:
        """Get the fallback chain as a list of providers."""
        return [self._providers[name] for name in self._fallback_chain if name in self._providers]

    def execute_with_fallback(
        self,
        method_name: str,
        *args,
        primary_only: bool = False,
        **kwargs,
    ):
        """
        Execute a method on the primary provider with fallback support.

        Args:
            method_name: Name of the method to call (e.g., 'generate', 'stream_generate')
            primary_only: If True, don't try fallbacks
            *args, **kwargs: Arguments to pass to the method

        Returns:
            Result from the first successful provider

        Raises:
            ProviderError: If all providers fail
        """
        if method_name == "stream_generate":
            return self._stream_with_fallback(*args, primary_only=primary_only, **kwargs)

        # Try primary provider first
        primary = self.get_primary()
        if primary:
            try:
                method = getattr(primary, method_name)
                return method(*args, **kwargs)
            except ProviderError as e:
                logger.warning("Primary provider '%s' failed: %s", primary.provider_name, e.kind)
                if primary_only:
                    raise
            except Exception as e:
                logger.warning("Primary provider '%s' failed with unexpected %s", primary.provider_name, type(e).__name__)
                if primary_only:
                    raise ProviderError("unknown_error", str(e), 500, original_exception=e) from e

        # Try fallback providers
        for fallback in self.get_fallback_chain():
            try:
                method = getattr(fallback, method_name)
                logger.info("Falling back to provider: %s", fallback.provider_name)
                return method(*args, **kwargs)
            except ProviderError as e:
                logger.warning("Fallback provider '%s' failed: %s", fallback.provider_name, e.kind)
                continue
            except Exception as e:
                logger.warning("Fallback provider '%s' failed with unexpected %s", fallback.provider_name, type(e).__name__)
                continue

        # All providers failed
        raise ProviderError(
            kind="all_providers_failed",
            user_message="All LLM providers failed to respond.",
            status_code=503,
        )

    @staticmethod
    def _without_duplicate_prefix(chunk: str, emitted: str) -> str:
        if not emitted or not chunk:
            return chunk
        if chunk.startswith(emitted):
            return chunk[len(emitted):]
        for size in range(min(len(emitted), len(chunk)), 0, -1):
            if emitted[-size:] == chunk[:size]:
                return chunk[size:]
        return chunk

    def _stream_with_fallback(self, *args, primary_only: bool = False, **kwargs):
        providers = []
        primary = self.get_primary()
        if primary:
            providers.append(primary)
        if not primary_only:
            providers.extend(self.get_fallback_chain())

        emitted = ""
        last_error = None
        for provider in providers:
            try:
                stream = getattr(provider, "stream_generate")(*args, **kwargs)
                for chunk in stream:
                    if not chunk:
                        continue
                    chunk = self._without_duplicate_prefix(chunk, emitted)
                    if chunk:
                        emitted += chunk
                        yield chunk
                return
            except ProviderError as exc:
                last_error = exc
                logger.warning("Provider '%s' stream failed: %s", provider.provider_name, exc.kind)
            except Exception as exc:
                last_error = exc
                logger.warning("Provider '%s' stream failed with unexpected %s", provider.provider_name, type(exc).__name__)

        if last_error and primary_only:
            raise last_error
        raise ProviderError(
            kind="all_providers_failed",
            user_message="All LLM providers failed to respond.",
            status_code=503,
            original_exception=last_error if isinstance(last_error, Exception) else None,
        )

    async def aexecute_with_fallback(
        self,
        method_name: str,
        *args,
        primary_only: bool = False,
        **kwargs,
    ):
        """Execute an async method with fallback support."""
        if method_name == "astream_generate":
            return self._astream_with_fallback(*args, primary_only=primary_only, **kwargs)

        primary = self.get_primary()
        if primary:
            try:
                method = getattr(primary, method_name)
                return await method(*args, **kwargs)
            except ProviderError as e:
                logger.warning("Primary provider '%s' failed: %s", primary.provider_name, e.kind)
                if primary_only:
                    raise
            except Exception as e:
                logger.warning("Primary provider '%s' failed with unexpected %s", primary.provider_name, type(e).__name__)
                if primary_only:
                    raise ProviderError("unknown_error", str(e), 500, original_exception=e) from e

        for fallback in self.get_fallback_chain():
            try:
                method = getattr(fallback, method_name)
                logger.info("Falling back to provider: %s", fallback.provider_name)
                return await method(*args, **kwargs)
            except ProviderError as e:
                logger.warning("Fallback provider '%s' failed: %s", fallback.provider_name, e.kind)
                continue
            except Exception as e:
                logger.warning("Fallback provider '%s' failed with unexpected %s", fallback.provider_name, type(e).__name__)
                continue

        raise ProviderError(
            kind="all_providers_failed",
            user_message="All LLM providers failed to respond.",
            status_code=503,
        )

    async def _astream_with_fallback(self, *args, primary_only: bool = False, **kwargs):
        providers = []
        primary = self.get_primary()
        if primary:
            providers.append(primary)
        if not primary_only:
            providers.extend(self.get_fallback_chain())

        emitted = ""
        last_error = None
        for provider in providers:
            try:
                stream = getattr(provider, "astream_generate")(*args, **kwargs)
                async for chunk in stream:
                    if not chunk:
                        continue
                    chunk = self._without_duplicate_prefix(chunk, emitted)
                    if chunk:
                        emitted += chunk
                        yield chunk
                return
            except ProviderError as exc:
                last_error = exc
                logger.warning("Provider '%s' async stream failed: %s", provider.provider_name, exc.kind)
            except Exception as exc:
                last_error = exc
                logger.warning("Provider '%s' async stream failed with unexpected %s", provider.provider_name, type(exc).__name__)

        if last_error and primary_only:
            raise last_error
        raise ProviderError(
            kind="all_providers_failed",
            user_message="All LLM providers failed to respond.",
            status_code=503,
            original_exception=last_error if isinstance(last_error, Exception) else None,
        )

    def close_all(self):
        """Close all providers."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                provider.close()
            if hasattr(provider, "aclose"):
                # Can't await here, but we can note it
                pass


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Get or create the global provider registry."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def configure_providers_from_env() -> ProviderRegistry:
    """Configure providers from environment variables."""
    registry = get_registry()
    registry._providers.clear()
    registry._primary_provider = None
    registry._fallback_chain.clear()

    # Determine which provider should be primary
    ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()
    model_router_provider = os.getenv("MODEL_ROUTER_PROVIDER", "").lower()

    # OmniRoute configuration
    omniroute_base_url = os.getenv("OMNIROUTE_BASE_URL")
    omniroute_api_key = os.getenv("OMNIROUTE_API_KEY")
    omniroute_model = os.getenv("OMNIROUTE_MODEL", "auto/best-chat")

    # Ollama configuration
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
    ollama_code_model = os.getenv("OLLAMA_CODE_MODEL", "codellama:7b")
    ollama_extra = {
        "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "4096")),
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "10m"),
    }

    # Gemini configuration
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    gemini_text_model = os.getenv("GEMINI_TEXT_MODEL", "gemini-1.5-flash")
    gemini_vision_model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    gemini_extra = {
        "max_retries": int(os.getenv("GEMINI_MAX_RETRIES", "2")),
        "base_delay": float(os.getenv("GEMINI_BASE_DELAY", "1.0")),
        "max_delay": float(os.getenv("GEMINI_MAX_DELAY", "8.0")),
    }

    # Determine effective primary provider
    # If MODEL_ROUTER_PROVIDER is set, use it; otherwise use AI_PROVIDER
    effective_primary = model_router_provider or ai_provider

    # Register OmniRoute if configured
    if omniroute_base_url and omniroute_api_key:
        omni_config = ProviderConfig(
            name="omniroute",
            model=omniroute_model,
            api_key=omniroute_api_key,
            base_url=omniroute_base_url,
            timeout=float(os.getenv("OMNIROUTE_TIMEOUT", "60")),
        )
        registry.register("omniroute", OmniRouteProvider(omni_config),
                         is_primary=(effective_primary == "omniroute"),
                         is_fallback=(effective_primary != "omniroute"))
        logger.info("OmniRoute provider registered (primary=%s)", effective_primary == "omniroute")

    # Register Ollama
    ollama_config = ProviderConfig(
        name="ollama",
        model=ollama_model,
        api_key=ollama_api_key if ollama_api_key else None,
        base_url=ollama_base_url,
        extra=ollama_extra,
    )
    registry.register("ollama", OllamaProvider(ollama_config),
                     is_primary=(effective_primary == "ollama" and not (omniroute_base_url and omniroute_api_key and effective_primary == "omniroute")),
                     is_fallback=True)
    logger.info("Ollama provider registered (primary=%s)", effective_primary == "ollama")

    # Register Ollama Code model as separate provider for code tasks
    ollama_code_config = ProviderConfig(
        name="ollama_code",
        model=ollama_code_model,
        api_key=ollama_api_key if ollama_api_key else None,
        base_url=ollama_base_url,
        extra=ollama_extra,
    )
    registry.register("ollama_code", OllamaProvider(ollama_code_config),
                     is_primary=False,
                     is_fallback=True)

    # Register Gemini if API key is available
    if gemini_api_key:
        gemini_config = ProviderConfig(
            name="gemini",
            model=gemini_text_model,
            api_key=gemini_api_key,
            extra=gemini_extra,
        )
        registry.register("gemini", GeminiProvider(gemini_config),
                         is_primary=(effective_primary == "gemini" and not (omniroute_base_url and omniroute_api_key and effective_primary == "omniroute")),
                         is_fallback=True)
        logger.info("Gemini provider registered (primary=%s)", effective_primary == "gemini")

    # If no primary was explicitly set, default to OmniRoute if available, then Ollama
    if not registry._primary_provider:
        if "omniroute" in registry._providers:
            registry._primary_provider = "omniroute"
            logger.info("Defaulting to OmniRoute as primary provider")
        elif "ollama" in registry._providers:
            registry._primary_provider = "ollama"
            logger.info("Defaulting to Ollama as primary provider")
        elif "gemini" in registry._providers:
            registry._primary_provider = "gemini"
            logger.info("Defaulting to Gemini as primary provider")

    return registry