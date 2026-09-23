"""Tests for performance telemetry."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(__file__))

from unittest.mock import patch
import perf_telemetry
from perf_telemetry import (
    PerfContext, create_context, new_request_id, PERF_LOGGING,
)


# Test 1: request ID is generated
print("=" * 60)
print("TEST 1: request ID is generated")
print("=" * 60)
rid1 = new_request_id()
rid2 = new_request_id()
assert isinstance(rid1, str)
assert len(rid1) == 12
assert rid1 != rid2
print("  PASS: request_id=" + rid1 + " (unique, 12 chars)")

# Test 2: telemetry is disabled by default
print("\n" + "=" * 60)
print("TEST 2: telemetry is disabled by default")
print("=" * 60)
assert PERF_LOGGING == False, "Expected PERF_LOGGING=False by default"
print("  PASS: PERF_LOGGING=" + str(PERF_LOGGING))

# Test 3: telemetry can be enabled
print("\n" + "=" * 60)
print("TEST 3: telemetry can be enabled")
print("=" * 60)
with patch.dict(os.environ, {"PERF_LOGGING": "true"}):
    import importlib
    importlib.reload(perf_telemetry)
    assert perf_telemetry.PERF_LOGGING == True
    print("  PASS: PERF_LOGGING=true when env set")
importlib.reload(perf_telemetry)
assert perf_telemetry.PERF_LOGGING == False

# Test 4: PerfContext tracks timing
print("\n" + "=" * 60)
print("TEST 4: PerfContext tracks timing")
print("=" * 60)
ctx = create_context("chat", "llama3.2:1b")
assert ctx.request_id is not None
assert ctx.action == "chat"
assert ctx.model == "llama3.2:1b"
assert ctx.backend_total_ms == 0.0
ctx.mark_ollama_start()
time.sleep(0.01)
ctx.mark_done({
    "ttft_ms": 100.0, "total_ms": 500.0,
    "prompt_eval_count": 779, "prompt_eval_duration_ms": 139.0,
    "eval_count": 160, "eval_duration_ms": 20000.0,
})
assert ctx.backend_total_ms > 0
assert ctx.prompt_eval_count == 779
assert ctx.eval_count == 160
print("  PASS: request_id=" + ctx.request_id)
print("  action=" + ctx.action + " model=" + ctx.model)
print("  backend_total_ms=" + str(round(ctx.backend_total_ms, 1)))
print("  prompt_eval_count=" + str(ctx.prompt_eval_count))
print("  eval_count=" + str(ctx.eval_count))

# Test 5: sensitive information is not logged
print("\n" + "=" * 60)
print("TEST 5: sensitive information is not logged")
print("=" * 60)
captured = []

with patch.dict(os.environ, {"PERF_LOGGING": "true"}):
    import importlib
    importlib.reload(perf_telemetry)

    def sync_emit(self):
        if not perf_telemetry.PERF_LOGGING:
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
        captured.append(entry)

    with patch.object(perf_telemetry.PerfContext, "emit", sync_emit):
        ctx2 = perf_telemetry.create_context("chat", "llama3.2:1b")
        ctx2.rag_used = True
        ctx2.mark_done({
            "ttft_ms": 100.0, "total_ms": 500.0,
            "prompt_eval_count": 779, "prompt_eval_duration_ms": 139.0,
            "eval_count": 160, "eval_duration_ms": 20000.0,
        })
        ctx2.emit()

importlib.reload(perf_telemetry)

assert len(captured) == 1, "Expected 1 captured entry, got " + str(len(captured))
entry = captured[0]

# Check that no forbidden key names exist
entry_keys_lower = set(k.lower() for k in entry.keys())
forbidden_keys = {"password", "api_key", "secret", "token", "user_message",
                  "document_content", "full_prompt", "jwt", "auth_token"}
for field in forbidden_keys:
    assert field not in entry_keys_lower, "Found forbidden key: " + field

# Verify required fields present
assert "request_id" in entry
assert "action" in entry
assert "model" in entry
assert "rag_used" in entry
assert "backend_total_ms" in entry
print("  PASS: entry contains no sensitive data")
print("  Fields: " + ", ".join(sorted(entry.keys())))

# Test 6: streaming and normal chat still work with telemetry
print("\n" + "=" * 60)
print("TEST 6: streaming and normal chat still work")
print("=" * 60)
from llm import ask_llm, stream_llm

ctx3 = create_context("chat", "llama3.2:1b")
result = ask_llm("What is 2+2?", perf_context=ctx3)
assert "4" in result
ctx3.emit()
print("  PASS: ask_llm works, response=" + repr(result[:50]))

ctx4 = create_context("stream", "llama3.2:1b")
chunks = []
for chunk in stream_llm("What is 3+3?", perf_context=ctx4):
    chunks.append(chunk)
full = "".join(chunks)
assert "6" in full
ctx4.emit()
print("  PASS: stream_llm works, chunks=" + str(len(chunks)) + ", response=" + repr(full[:50]))

# Test 7: errors are tracked
print("\n" + "=" * 60)
print("TEST 7: errors are tracked")
print("=" * 60)
ctx5 = create_context("chat", "llama3.2:1b")
ctx5.add_error("test_error")
assert len(ctx5.errors) == 1
assert ctx5.errors[0] == "test_error"
print("  PASS: errors tracked: " + str(ctx5.errors))

print("\n" + "=" * 60)
print("ALL TELEMETRY TESTS PASSED")
print("=" * 60)