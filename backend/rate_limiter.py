"""Rate limiting utilities for API endpoints."""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from fastapi import HTTPException, Request, Depends

from auth import get_current_user


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int
    window_seconds: int
    key_prefix: str = "ratelimit"
    algorithm: str = "sliding_window"  # "token_bucket" or "sliding_window"


@dataclass
class TokenBucket:
    """Thread-safe token bucket for rate limiting."""
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    last_access: float = field(default_factory=time.monotonic, init=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        """Try to consume tokens. Returns (success, retry_after_seconds)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            self.last_access = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            else:
                retry_after = (tokens - self.tokens) / self.refill_rate
                return False, retry_after


@dataclass
class SlidingWindowBucket:
    """Thread-safe sliding window rate limiter."""
    max_requests: int
    window_seconds: int
    requests: List[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    last_access: float = field(default_factory=time.monotonic, init=False)

    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        """Try to consume tokens. Returns (success, retry_after_seconds)."""
        with self._lock:
            now = time.monotonic()
            self.last_access = now

            # Remove requests outside the window
            window_start = now - self.window_seconds
            self.requests = [ts for ts in self.requests if ts > window_start]

            if len(self.requests) + tokens <= self.max_requests:
                # Add current request timestamps
                self.requests.extend([now] * tokens)
                return True, 0.0
            else:
                # Calculate when the oldest request will expire
                oldest = self.requests[0]
                retry_after = (oldest + self.window_seconds) - now
                return False, max(retry_after, 0.01)


class RateLimiter:
    """In-memory rate limiter with per-key buckets and automatic cleanup."""

    def __init__(self, cleanup_interval_seconds: int = 300, max_idle_seconds: int = 3600):
        self._token_buckets: Dict[str, TokenBucket] = {}
        self._sliding_buckets: Dict[str, SlidingWindowBucket] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
        self._lock = threading.Lock()
        self._cleanup_interval = cleanup_interval_seconds
        self._max_idle_seconds = max_idle_seconds
        self._last_cleanup = time.monotonic()

    def configure(self, name: str, config: RateLimitConfig) -> None:
        """Configure a rate limit rule."""
        with self._lock:
            self._configs[name] = config

    def _maybe_cleanup(self) -> None:
        """Clean up stale buckets if cleanup interval has passed."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        cutoff = now - self._max_idle_seconds

        # Clean token buckets
        stale_token_keys = [
            k for k, b in self._token_buckets.items()
            if b.last_access < cutoff
        ]
        for k in stale_token_keys:
            del self._token_buckets[k]

        # Clean sliding window buckets
        stale_sliding_keys = [
            k for k, b in self._sliding_buckets.items()
            if b.last_access < cutoff
        ]
        for k in stale_sliding_keys:
            del self._sliding_buckets[k]

    def _get_token_bucket(self, key: str, config: RateLimitConfig) -> TokenBucket:
        """Get or create a token bucket for the key."""
        with self._lock:
            self._maybe_cleanup()
            if key not in self._token_buckets or self._token_buckets[key].capacity != config.requests:
                self._token_buckets[key] = TokenBucket(
                    capacity=config.requests,
                    refill_rate=config.requests / config.window_seconds
                )
            return self._token_buckets[key]

    def _get_sliding_bucket(self, key: str, config: RateLimitConfig) -> SlidingWindowBucket:
        """Get or create a sliding window bucket for the key."""
        with self._lock:
            self._maybe_cleanup()
            if key not in self._sliding_buckets:
                self._sliding_buckets[key] = SlidingWindowBucket(
                    max_requests=config.requests,
                    window_seconds=config.window_seconds
                )
            return self._sliding_buckets[key]

    def check_limit(self, name: str, key: str, tokens: int = 1) -> tuple[bool, Optional[float]]:
        """
        Check if request is within rate limit.
        Returns (allowed, retry_after_seconds).
        """
        config = self._configs.get(name)
        if not config:
            return True, None  # No limit configured

        bucket_key = f"{config.key_prefix}:{name}:{key}"

        if config.algorithm == "sliding_window":
            bucket = self._get_sliding_bucket(bucket_key, config)
        else:
            bucket = self._get_token_bucket(bucket_key, config)

        return bucket.consume(tokens)

    def get_current_usage(self, name: str, key: str) -> dict:
        """Get current usage statistics for a rate limit key."""
        config = self._configs.get(name)
        if not config:
            return {"configured": False}

        bucket_key = f"{config.key_prefix}:{name}:{key}"

        if config.algorithm == "sliding_window":
            bucket = self._sliding_buckets.get(bucket_key)
            if not bucket:
                return {"configured": True, "used": 0, "remaining": config.requests, "reset_after_seconds": config.window_seconds}
            with bucket._lock:
                now = time.monotonic()
                window_start = now - config.window_seconds
                valid_requests = [ts for ts in bucket.requests if ts > window_start]
                return {
                    "configured": True,
                    "used": len(valid_requests),
                    "remaining": max(0, config.requests - len(valid_requests)),
                    "reset_after_seconds": config.window_seconds,
                    "window_seconds": config.window_seconds,
                }
        else:
            bucket = self._token_buckets.get(bucket_key)
            if not bucket:
                return {"configured": True, "used": 0, "remaining": config.requests, "reset_after_seconds": config.window_seconds}
            with bucket._lock:
                return {
                    "configured": True,
                    "used": int(config.requests - bucket.tokens),
                    "remaining": int(bucket.tokens),
                    "reset_after_seconds": config.window_seconds,
                    "window_seconds": config.window_seconds,
                }


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


def ip_rate_limit(limit_name: str, tokens: int = 1):
    """Create a per-IP rate limit dependency for unauthenticated endpoints."""
    async def rate_limit_check(request: Request):
        key = get_client_ip(request)
        allowed, retry_after = rate_limiter.check_limit(limit_name, key, tokens)

        if not allowed:
            from app import logger
            logger.warning("Rate limit exceeded: %s for IP %s", limit_name, key)

            raise HTTPException(
                status_code=429,
                detail={
                    "error": True,
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after_seconds": int(retry_after) + 1,
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        request.state.rate_limit_info = {
            "limit_name": limit_name,
            "key": key,
        }

    return rate_limit_check


def user_rate_limit(limit_name: str, tokens: int = 1):
    """Create a per-user rate limit dependency for authenticated endpoints."""
    async def rate_limit_check(request: Request, user_id: int = Depends(get_current_user)):
        key = f"user:{user_id}"
        allowed, retry_after = rate_limiter.check_limit(limit_name, key, tokens)

        if not allowed:
            from app import logger
            logger.warning("Rate limit exceeded: %s for %s", limit_name, key)

            raise HTTPException(
                status_code=429,
                detail={
                    "error": True,
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after_seconds": int(retry_after) + 1,
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        request.state.rate_limit_info = {
            "limit_name": limit_name,
            "key": key,
        }

    return rate_limit_check


def tool_rate_limit(limit_name: str, tokens: int = 1):
    """Create a per-user+tool rate limit dependency for tool execution protection."""
    async def rate_limit_check(request: Request, user_id: int = Depends(get_current_user)):
        # Tool name extracted from request path or body
        tool_name = getattr(request.state, "tool_name", "unknown")
        key = f"user:{user_id}:tool:{tool_name}"
        allowed, retry_after = rate_limiter.check_limit(limit_name, key, tokens)

        if not allowed:
            from app import logger
            logger.warning("Tool rate limit exceeded: %s for %s", limit_name, key)

            raise HTTPException(
                status_code=429,
                detail={
                    "error": True,
                    "code": "tool_rate_limit_exceeded",
                    "message": "Tool rate limit exceeded. Please wait before retrying.",
                    "retry_after_seconds": int(retry_after) + 1,
                },
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        request.state.rate_limit_info = {
            "limit_name": limit_name,
            "key": key,
        }

    return rate_limit_check


def configure_default_limits():
    """Configure default rate limits from environment variables."""
    import os

    # Unauthenticated endpoints - per IP (sliding window for clean reset)
    rate_limiter.configure("register", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_REGISTER", "5")),
        window_seconds=int(os.getenv("RATE_LIMIT_REGISTER_WINDOW", "300")),
        key_prefix="ip",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("login", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_LOGIN", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_LOGIN_WINDOW", "300")),
        key_prefix="ip",
        algorithm="sliding_window"
    ))

    # Authenticated endpoints - per user (sliding window for clean reset)
    rate_limiter.configure("chat", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_CHAT", "30")),
        window_seconds=int(os.getenv("RATE_LIMIT_CHAT_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("stream", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_STREAM", "20")),
        window_seconds=int(os.getenv("RATE_LIMIT_STREAM_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("vision", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_VISION", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_VISION_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("generate_image", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_GENERATE_IMAGE", "5")),
        window_seconds=int(os.getenv("RATE_LIMIT_GENERATE_IMAGE_WINDOW", "300")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("upload", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_UPLOAD", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_UPLOAD_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("upload_files", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_UPLOAD_FILES", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_UPLOAD_FILES_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # Project endpoints
    rate_limiter.configure("projects", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_PROJECTS", "30")),
        window_seconds=int(os.getenv("RATE_LIMIT_PROJECTS_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("project_files", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_PROJECT_FILES", "20")),
        window_seconds=int(os.getenv("RATE_LIMIT_PROJECT_FILES_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # Tool execution protection - per user per tool
    rate_limiter.configure("tool_execution", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_TOOL_EXECUTION", "50")),
        window_seconds=int(os.getenv("RATE_LIMIT_TOOL_EXECUTION_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # Web search and Python execution - stricter limits
    rate_limiter.configure("web_search", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_WEB_SEARCH", "20")),
        window_seconds=int(os.getenv("RATE_LIMIT_WEB_SEARCH_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("python_exec", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_PYTHON_EXEC", "30")),
        window_seconds=int(os.getenv("RATE_LIMIT_PYTHON_EXEC_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # Memory operations
    rate_limiter.configure("memory", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_MEMORY", "40")),
        window_seconds=int(os.getenv("RATE_LIMIT_MEMORY_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # Voice endpoints
    rate_limiter.configure("voice_transcribe", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_VOICE_TRANSCRIBE", "15")),
        window_seconds=int(os.getenv("RATE_LIMIT_VOICE_TRANSCRIBE_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))
    rate_limiter.configure("voice_chat", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_VOICE_CHAT", "15")),
        window_seconds=int(os.getenv("RATE_LIMIT_VOICE_CHAT_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))

    # RAG operations
    rate_limiter.configure("rag_search", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_RAG_SEARCH", "30")),
        window_seconds=int(os.getenv("RATE_LIMIT_RAG_SEARCH_WINDOW", "60")),
        key_prefix="user",
        algorithm="sliding_window"
    ))