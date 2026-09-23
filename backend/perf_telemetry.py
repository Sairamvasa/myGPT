"""Lightweight performance telemetry for MyGPT backend.

Adds structured, non-blocking performance logging for chat/stream requests.
Disabled by default (PERF_LOGGING=false). When enabled, emits one compact
JSON log entry per request with timing and Ollama metrics.

Never logs: API keys, tokens, passwords, full user messages, prompts, or
uploaded document contents.
"""

import os
import json
import time
import uuid
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger("MyGPT.Perf")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PERF_LOGGING = os.getenv("PERF_LOGGING", "false").lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------
class PerfContext:
    """Tracks timing and metrics for a single request."""

    __slots__ = [
        "request_id", "action", "model", "rag_used",
        "retrieval_ms", "prompt_build_ms",
        "ollama_ttft_ms", "ollama_total_ms",
        "prompt_eval_count", "prompt_eval_duration_ms",
        "eval_count", "eval_duration_ms",
        "backend_total_ms",
        "start_time", "ollama_start_time", "first_token_time",
        "errors",
    ]

    def __init__(self, request_id: str, action: str, model: str):
        self.request_id = request_id
        self.action = action
        self.model = model
        self.rag_used = False
        self.retrieval_ms = 0.0
        self.prompt_build_ms = 0.0
        self.ollama_ttft_ms = 0.0
        self.ollama_total_ms = 0.0
        self.prompt_eval_count = 0
        self.prompt_eval_duration_ms = 0.0
        self.eval_count = 0
        self.eval_duration_ms = 0.0
        self.backend_total_ms = 0.0
        self.start_time = time.perf_counter()
        self.ollama_start_time = 0.0
        self.first_token_time = 0.0
        self.errors = []

    def mark_ollama_start(self):
        self.ollama_start_time = time.perf_counter()

    def mark_first_token(self):
        if self.ollama_start_time > 0:
            self.first_token_time = (time.perf_counter() - self.ollama_start_time) * 1000

    def mark_done(self, ollama_metrics: Optional[Dict[str, Any]] = None):
        if ollama_metrics:
            self.ollama_ttft_ms = ollama_metrics.get("ttft_ms", 0.0)
            self.ollama_total_ms = ollama_metrics.get("total_ms", 0.0)
            self.prompt_eval_count = ollama_metrics.get("prompt_eval_count", 0)
            self.prompt_eval_duration_ms = ollama_metrics.get("prompt_eval_duration_ms", 0.0)
            self.eval_count = ollama_metrics.get("eval_count", 0)
            self.eval_duration_ms = ollama_metrics.get("eval_duration_ms", 0.0)
        self.backend_total_ms = (time.perf_counter() - self.start_time) * 1000

    def add_error(self, msg: str):
        self.errors.append(msg)

    def emit(self):
        """Emit a single compact structured log entry."""
        if not PERF_LOGGING:
            return
        entry = {
            "request_id": self.request_id,
            "action": self.action,
            "model": self.model,
            "rag_used": self.rag_used,
            "retrieval_ms": round(self.retrieval_ms, 1),
            "prompt_build_ms": round(self.prompt_build_ms, 1),
            "ollama_ttft_ms": round(self.ollama_ttft_ms, 1),
            "ollama_total_ms": round(self.ollama_total_ms, 1),
            "prompt_eval_count": self.prompt_eval_count,
            "prompt_eval_duration_ms": round(self.prompt_eval_duration_ms, 1),
            "eval_count": self.eval_count,
            "eval_duration_ms": round(self.eval_duration_ms, 1),
            "backend_total_ms": round(self.backend_total_ms, 1),
        }
        if self.errors:
            entry["errors"] = self.errors
        # Non-blocking: use a daemon thread so it never delays the response.
        threading.Thread(target=_safe_log, args=(entry,), daemon=True).start()


def _safe_log(entry: Dict[str, Any]):
    """Emit log entry in a fire-and-forget thread."""
    try:
        logger.info("PERF " + json.dumps(entry, separators=(",", ":")))
    except Exception:
        pass  # never let telemetry break the request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def new_request_id() -> str:
    """Generate a short unique request ID."""
    return uuid.uuid4().hex[:12]


def create_context(action: str, model: str) -> PerfContext:
    """Create a new PerfContext for a request."""
    return PerfContext(new_request_id(), action, model)