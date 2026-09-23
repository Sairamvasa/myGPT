"""Rate limiting utilities for API endpoints."""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit rule."""
    requests: int
    window_seconds: int
    key_prefix: str = "ratelimit"


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> tuple[bool, float]:
        """Try to consume tokens. Returns (success, retry_after_seconds)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            else:
                retry_after = (tokens - self.tokens) / self.refill_rate
                return False, retry_after


class RateLimiter:
    """In-memory rate limiter with per-key token buckets."""
    
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(1, 1.0)  # placeholder, will be replaced on first use
        )
        self._configs: dict[str, RateLimitConfig] = {}
        self._lock = threading.Lock()
    
    def configure(self, name: str, config: RateLimitConfig) -> None:
        """Configure a rate limit rule."""
        self._configs[name] = config
    
    def _get_bucket(self, key: str, config: RateLimitConfig) -> TokenBucket:
        """Get or create a token bucket for the key."""
        with self._lock:
            if key not in self._buckets or self._buckets[key].capacity != config.requests:
                self._buckets[key] = TokenBucket(
                    capacity=config.requests,
                    refill_rate=config.requests / config.window_seconds
                )
            return self._buckets[key]
    
    def check_limit(self, name: str, key: str, tokens: int = 1) -> tuple[bool, Optional[float]]:
        """
        Check if request is within rate limit.
        Returns (allowed, retry_after_seconds).
        """
        config = self._configs.get(name)
        if not config:
            return True, None  # No limit configured
        
        bucket_key = f"{config.key_prefix}:{name}:{key}"
        bucket = self._get_bucket(bucket_key, config)
        return bucket.consume(tokens)


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
            logger.warning("Rate limit exceeded: %s for %s", limit_name, key)
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": True,
                    "code": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded for {limit_name}. Please try again later.",
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
                    "message": f"Rate limit exceeded for {limit_name}. Please try again later.",
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
    
    # Unauthenticated endpoints - per IP
    rate_limiter.configure("register", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_REGISTER", "5")),
        window_seconds=int(os.getenv("RATE_LIMIT_REGISTER_WINDOW", "300")),
        key_prefix="ip"
    ))
    rate_limiter.configure("login", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_LOGIN", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_LOGIN_WINDOW", "300")),
        key_prefix="ip"
    ))
    
    # Authenticated endpoints - per user
    rate_limiter.configure("chat", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_CHAT", "30")),
        window_seconds=int(os.getenv("RATE_LIMIT_CHAT_WINDOW", "60")),
        key_prefix="user"
    ))
    rate_limiter.configure("stream", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_STREAM", "20")),
        window_seconds=int(os.getenv("RATE_LIMIT_STREAM_WINDOW", "60")),
        key_prefix="user"
    ))
    rate_limiter.configure("vision", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_VISION", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_VISION_WINDOW", "60")),
        key_prefix="user"
    ))
    rate_limiter.configure("generate_image", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_GENERATE_IMAGE", "5")),
        window_seconds=int(os.getenv("RATE_LIMIT_GENERATE_IMAGE_WINDOW", "300")),
        key_prefix="user"
    ))
    rate_limiter.configure("upload", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_UPLOAD", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_UPLOAD_WINDOW", "60")),
        key_prefix="user"
    ))
    rate_limiter.configure("upload_files", RateLimitConfig(
        requests=int(os.getenv("RATE_LIMIT_UPLOAD_FILES", "10")),
        window_seconds=int(os.getenv("RATE_LIMIT_UPLOAD_FILES_WINDOW", "60")),
        key_prefix="user"
    ))