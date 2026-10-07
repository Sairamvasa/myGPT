"""Rate limiting tests for MyGPT."""

import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import Request
from starlette.datastructures import Headers

from rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    TokenBucket,
    SlidingWindowBucket,
    get_client_ip,
    configure_default_limits,
)


class TestTokenBucket:
    def test_initial_tokens_available(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        allowed, retry = bucket.consume(5)
        assert allowed is True
        assert retry == 0.0

    def test_consume_exceeds_capacity(self):
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        allowed, retry = bucket.consume(6)
        assert allowed is False
        assert retry > 0

    def test_refill_over_time(self):
        bucket = TokenBucket(capacity=10, refill_rate=10.0)  # 10 tokens/sec
        bucket.consume(10)
        assert bucket.tokens == 0

        time.sleep(0.15)  # 1.5 tokens should refill
        allowed, retry = bucket.consume(1)
        assert allowed is True

    def test_thread_safety(self):
        import threading
        bucket = TokenBucket(capacity=100, refill_rate=100.0)
        results = []

        def consume_tokens():
            allowed, _ = bucket.consume(10)
            results.append(allowed)

        threads = [threading.Thread(target=consume_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 10


class TestSlidingWindowBucket:
    def test_allows_requests_within_limit(self):
        bucket = SlidingWindowBucket(max_requests=10, window_seconds=60)
        for _ in range(10):
            allowed, _ = bucket.consume()
            assert allowed is True

    def test_blocks_when_limit_exceeded(self):
        bucket = SlidingWindowBucket(max_requests=5, window_seconds=60)
        for _ in range(5):
            bucket.consume()
        allowed, retry = bucket.consume()
        assert allowed is False
        assert retry > 0

    def test_window_reset_allows_new_requests(self):
        bucket = SlidingWindowBucket(max_requests=3, window_seconds=1)
        for _ in range(3):
            bucket.consume()
        allowed, _ = bucket.consume()
        assert allowed is False

        time.sleep(1.1)
        allowed, _ = bucket.consume()
        assert allowed is True

    def test_partial_window_reset(self):
        bucket = SlidingWindowBucket(max_requests=5, window_seconds=2)
        for _ in range(5):
            bucket.consume()
        time.sleep(1)  # Half window passed
        # Should still be blocked
        allowed, _ = bucket.consume()
        assert allowed is False

        time.sleep(1.1)  # Full window passed
        allowed, _ = bucket.consume()
        assert allowed is True

    def test_multiple_tokens_at_once(self):
        bucket = SlidingWindowBucket(max_requests=10, window_seconds=60)
        allowed, _ = bucket.consume(3)
        assert allowed is True
        allowed, _ = bucket.consume(7)
        assert allowed is True
        allowed, _ = bucket.consume(1)
        assert allowed is False


class TestRateLimiter:
    def setup_method(self):
        self.limiter = RateLimiter(cleanup_interval_seconds=1, max_idle_seconds=2)

    def test_no_config_allows_all(self):
        allowed, retry = self.limiter.check_limit("nonexistent", "key1")
        assert allowed is True
        assert retry is None

    def test_configure_and_check_sliding_window(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=3, window_seconds=60, algorithm="sliding_window"
        ))
        for _ in range(3):
            allowed, _ = self.limiter.check_limit("test", "user:1")
            assert allowed is True
        allowed, retry = self.limiter.check_limit("test", "user:1")
        assert allowed is False
        assert retry > 0

    def test_configure_and_check_token_bucket(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=3, window_seconds=60, algorithm="token_bucket"
        ))
        for _ in range(3):
            allowed, _ = self.limiter.check_limit("test", "user:1")
            assert allowed is True
        allowed, retry = self.limiter.check_limit("test", "user:1")
        assert allowed is False
        assert retry > 0

    def test_different_keys_independent(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=2, window_seconds=60, algorithm="sliding_window"
        ))
        self.limiter.check_limit("test", "user:1")
        self.limiter.check_limit("test", "user:1")
        allowed, _ = self.limiter.check_limit("test", "user:2")
        assert allowed is True

    def test_different_limit_names_independent(self):
        self.limiter.configure("a", RateLimitConfig(requests=1, window_seconds=60))
        self.limiter.configure("b", RateLimitConfig(requests=1, window_seconds=60))
        self.limiter.check_limit("a", "user:1")
        allowed, _ = self.limiter.check_limit("b", "user:1")
        assert allowed is True

    def test_get_current_usage_sliding_window(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=5, window_seconds=60, algorithm="sliding_window"
        ))
        self.limiter.check_limit("test", "user:1")
        self.limiter.check_limit("test", "user:1")
        usage = self.limiter.get_current_usage("test", "user:1")
        assert usage["configured"] is True
        assert usage["used"] == 2
        assert usage["remaining"] == 3

    def test_get_current_usage_token_bucket(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=5, window_seconds=60, algorithm="token_bucket"
        ))
        self.limiter.check_limit("test", "user:1")
        self.limiter.check_limit("test", "user:1")
        usage = self.limiter.get_current_usage("test", "user:1")
        assert usage["configured"] is True
        # Token bucket used is approximate due to float math
        assert usage["used"] >= 1

    def test_cleanup_removes_stale_buckets(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=5, window_seconds=60, algorithm="sliding_window"
        ))
        self.limiter.check_limit("test", "user:1")
        # Key includes prefix
        assert any("user:1" in k for k in self.limiter._sliding_buckets)

        # Wait for cleanup interval and max idle
        time.sleep(3)

        # Trigger cleanup by checking a different key
        self.limiter.check_limit("test", "user:2")

        # Stale bucket should be removed
        assert not any("user:1" in k for k in self.limiter._sliding_buckets)

    def test_cleanup_does_not_remove_active_buckets(self):
        self.limiter.configure("test", RateLimitConfig(
            requests=5, window_seconds=60, algorithm="sliding_window"
        ))
        self.limiter.check_limit("test", "user:1")

        # Wait for cleanup interval but not max idle
        time.sleep(1.5)
        self.limiter.check_limit("test", "user:2")

        # Active bucket should remain
        assert any("user:1" in k for k in self.limiter._sliding_buckets)


class TestGetClientIP:
    def test_x_forwarded_for(self):
        request = MagicMock(spec=Request)
        request.headers = Headers({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        request.client = None
        assert get_client_ip(request) == "1.2.3.4"

    def test_x_real_ip(self):
        request = MagicMock(spec=Request)
        request.headers = Headers({"x-real-ip": "9.8.7.6"})
        request.client = None
        assert get_client_ip(request) == "9.8.7.6"

    def test_client_host(self):
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        assert get_client_ip(request) == "10.0.0.1"

    def test_unknown_when_no_info(self):
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = None
        assert get_client_ip(request) == "unknown"


class TestRateLimitDependencies:
    @pytest.mark.asyncio
    async def test_ip_rate_limit_allows(self):
        from rate_limiter import ip_rate_limit, rate_limiter
        rate_limiter.configure("test_ip", RateLimitConfig(
            requests=5, window_seconds=60, key_prefix="ip", algorithm="sliding_window"
        ))

        request = MagicMock(spec=Request)
        request.headers = Headers({"x-forwarded-for": "1.2.3.4"})
        request.client = None
        request.state = MagicMock()

        check = ip_rate_limit("test_ip")
        await check(request)
        assert hasattr(request.state, "rate_limit_info")

    @pytest.mark.asyncio
    async def test_ip_rate_limit_blocks(self):
        from rate_limiter import ip_rate_limit, rate_limiter
        rate_limiter.configure("test_ip_block", RateLimitConfig(
            requests=1, window_seconds=60, key_prefix="ip", algorithm="sliding_window"
        ))

        request = MagicMock(spec=Request)
        request.headers = Headers({"x-forwarded-for": "1.2.3.4"})
        request.client = None
        request.state = MagicMock()

        check = ip_rate_limit("test_ip_block")
        await check(request)  # First request allowed

        with pytest.raises(Exception) as exc_info:
            await check(request)  # Second request blocked

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["code"] == "rate_limit_exceeded"
        # Ensure no sensitive info leaked
        assert "password" not in str(exc_info.value.detail).lower()
        assert "token" not in str(exc_info.value.detail).lower()
        assert "secret" not in str(exc_info.value.detail).lower()
        assert "key" not in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_user_rate_limit_isolates_users(self):
        from rate_limiter import user_rate_limit, rate_limiter, get_current_user
        rate_limiter.configure("test_user", RateLimitConfig(
            requests=2, window_seconds=60, key_prefix="user", algorithm="sliding_window"
        ))

        # Test directly with the rate limiter to verify user isolation
        # User 1 makes 2 requests
        allowed, _ = rate_limiter.check_limit("test_user", "user:1")
        assert allowed is True
        allowed, _ = rate_limiter.check_limit("test_user", "user:1")
        assert allowed is True
        allowed, _ = rate_limiter.check_limit("test_user", "user:1")
        assert allowed is False

        # User 2 should still be allowed (independent limit)
        allowed, _ = rate_limiter.check_limit("test_user", "user:2")
        assert allowed is True
        allowed, _ = rate_limiter.check_limit("test_user", "user:2")
        assert allowed is True
        allowed, _ = rate_limiter.check_limit("test_user", "user:2")
        assert allowed is False

        # User 1 should still be blocked
        allowed, _ = rate_limiter.check_limit("test_user", "user:1")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_rate_limit_error_no_sensitive_info(self):
        from rate_limiter import user_rate_limit, rate_limiter
        rate_limiter.configure("test_sensitive", RateLimitConfig(
            requests=1, window_seconds=60, key_prefix="user", algorithm="sliding_window"
        ))

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        check = user_rate_limit("test_sensitive")

        with patch("rate_limiter.get_current_user", return_value=1):
            await check(request)
            with pytest.raises(Exception) as exc_info:
                await check(request)

        detail = exc_info.value.detail
        assert "password" not in str(detail).lower()
        assert "token" not in str(detail).lower()
        assert "secret" not in str(detail).lower()
        assert "apikey" not in str(detail).lower()
        assert "api_key" not in str(detail).lower()
        assert "1.2.3.4" not in str(detail)  # No IPs in error


class TestDefaultLimits:
    def test_configure_default_limits(self):
        # This should not raise
        configure_default_limits()

        # Verify some expected configs exist
        from rate_limiter import rate_limiter
        assert "chat" in rate_limiter._configs
        assert "stream" in rate_limiter._configs
        assert "vision" in rate_limiter._configs
        assert "tool_execution" in rate_limiter._configs
        assert "web_search" in rate_limiter._configs
        assert "python_exec" in rate_limiter._configs


class TestConcurrency:
    def test_concurrent_requests_thread_safe(self):
        limiter = RateLimiter()
        limiter.configure("concurrent", RateLimitConfig(
            requests=100, window_seconds=60, algorithm="sliding_window"
        ))

        import threading
        results = []

        def make_requests():
            for _ in range(10):
                allowed, _ = limiter.check_limit("concurrent", "user:1")
                results.append(allowed)

        threads = [threading.Thread(target=make_requests) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 100 should succeed
        assert sum(results) == 100

    def test_burst_then_sustained_rate(self):
        limiter = RateLimiter()
        limiter.configure("burst", RateLimitConfig(
            requests=10, window_seconds=1, algorithm="sliding_window"
        ))

        # Burst
        for _ in range(10):
            allowed, _ = limiter.check_limit("burst", "user:1")
            assert allowed is True

        # Should be blocked
        allowed, _ = limiter.check_limit("burst", "user:1")
        assert allowed is False

        # Wait for window
        time.sleep(1.1)

        # Should be allowed again
        allowed, _ = limiter.check_limit("burst", "user:1")
        assert allowed is True


class TestAbuseProtection:
    def test_rapid_fire_requests_blocked(self):
        limiter = RateLimiter()
        limiter.configure("abuse", RateLimitConfig(
            requests=5, window_seconds=1, algorithm="sliding_window"
        ))

        # Simulate rapid fire
        for i in range(20):
            allowed, retry = limiter.check_limit("abuse", "attacker")
            if i < 5:
                assert allowed is True
            else:
                assert allowed is False
                assert retry > 0

    def test_distributed_attack_isolation(self):
        """Multiple IPs/users should be independently limited."""
        limiter = RateLimiter()
        limiter.configure("ddos", RateLimitConfig(
            requests=10, window_seconds=60, algorithm="sliding_window"
        ))

        # Attacker 1
        for _ in range(10):
            assert limiter.check_limit("ddos", "ip:1.1.1.1")[0] is True
        assert limiter.check_limit("ddos", "ip:1.1.1.1")[0] is False

        # Attacker 2 should be unaffected
        for _ in range(10):
            assert limiter.check_limit("ddos", "ip:2.2.2.2")[0] is True
        assert limiter.check_limit("ddos", "ip:2.2.2.2")[0] is False


class TestIntegrationWithApp:
    @pytest.mark.asyncio
    async def test_chat_endpoint_rate_limited(self):
        from rate_limiter import rate_limiter, user_rate_limit
        from fastapi.testclient import TestClient

        # This tests the integration pattern - we just verify the dependency works
        rate_limiter.configure("chat_test", RateLimitConfig(
            requests=2, window_seconds=60, key_prefix="user", algorithm="sliding_window"
        ))

        request = MagicMock(spec=Request)
        request.state = MagicMock()
        check = user_rate_limit("chat_test")

        with patch("rate_limiter.get_current_user", return_value=42):
            await check(request)
            await check(request)
            with pytest.raises(Exception) as exc_info:
                await check(request)
            assert exc_info.value.status_code == 429