"""Focused regression tests for execution-timeout and resource-bound enforcement."""

import time

import pytest

import agents.execution_loop as execution_loop_module
from agents.execution_loop import AgentExecutor, ExecutionOutcome, ResourceLimits
from agents.tool_registry import RiskLevel, Tool, ToolRegistry, ToolResult


@pytest.fixture(autouse=True)
def _reset_tool_pool():
    ToolRegistry.shutdown_pool()
    yield
    ToolRegistry.shutdown_pool()


def _make_tool(
    name,
    *,
    output="",
    success=True,
    error=None,
    timed_out=False,
    timeout_seconds=0.25,
    executor=None,
):
    if executor is None:
        def _executor(args, ctx):
            return ToolResult(
                tool_name=name,
                success=success,
                output=output,
                error=error,
                observation=(output if output else ""),
                timed_out=timed_out,
            )

        executor = _executor

    return Tool(
        name=name,
        description=f"Test tool {name}",
        category="test",
        input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=timeout_seconds,
        executor=executor,
    )


def _make_registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_resource_limits_default_values():
    limits = ResourceLimits()

    assert limits.max_iterations == 5
    assert limits.max_tool_calls == 10
    assert limits.max_total_output_chars == 256_000
    assert limits.max_execution_seconds == 120
    assert limits.max_retries == 2


def test_resource_limits_support_custom_values():
    limits = ResourceLimits(
        max_iterations=3,
        max_tool_calls=4,
        max_total_output_chars=99,
        max_execution_seconds=7,
        max_retries=1,
    )

    assert limits.max_iterations == 3
    assert limits.max_tool_calls == 4
    assert limits.max_total_output_chars == 99
    assert limits.max_execution_seconds == 7
    assert limits.max_retries == 1


def test_agent_executor_accepts_legacy_max_iterations_kwarg():
    registry = ToolRegistry()
    executor = AgentExecutor(registry, max_iterations=7)

    assert executor.limits.max_iterations == 7
    assert executor.limits.max_execution_seconds == 120


def test_execution_outcome_tracks_timeout_and_count_fields():
    outcome = ExecutionOutcome()

    outcome.deadline_exceeded = True
    outcome.max_tool_calls_exceeded = True
    outcome.total_tool_calls = 3
    outcome.total_output_chars = 42

    assert outcome.deadline_exceeded is True
    assert outcome.max_tool_calls_exceeded is True
    assert outcome.total_tool_calls == 3
    assert outcome.total_output_chars == 42


def test_execute_stops_when_deadline_exceeded(monkeypatch):
    registry = _make_registry(_make_tool("web_search", output="done"))
    executor = AgentExecutor(registry, limits=ResourceLimits(max_iterations=5, max_execution_seconds=1))

    values = iter([0.0, 2.0, 2.5, 2.5])
    monkeypatch.setattr(execution_loop_module.time, "monotonic", lambda: next(values))

    outcome = executor.execute("search the web for Paris")

    assert outcome.deadline_exceeded is True
    assert "maximum time" in (outcome.error or "")


def test_execute_stops_when_max_tool_call_budget_is_hit():
    def slow_fail(args, ctx):
        return ToolResult(tool_name="web_search", success=False, error="temporary failure")

    registry = _make_registry(_make_tool("web_search", executor=slow_fail, timeout_seconds=0.25))
    executor = AgentExecutor(
        registry,
        limits=ResourceLimits(max_iterations=5, max_tool_calls=1, max_execution_seconds=30, max_retries=2),
    )

    outcome = executor.execute("search the web for Paris")

    assert outcome.max_tool_calls_exceeded is True
    assert outcome.total_tool_calls >= 1
    assert "Maximum tool calls" in (outcome.error or "")


def test_execute_stops_when_total_output_char_limit_is_hit():
    large_text = "x" * 128
    registry = _make_registry(_make_tool("web_search", output=large_text, timeout_seconds=0.25))
    executor = AgentExecutor(
        registry,
        limits=ResourceLimits(max_iterations=5, max_total_output_chars=10, max_execution_seconds=30),
    )

    outcome = executor.execute("search the web for Paris")

    assert outcome.error is not None
    assert "Accumulated tool output exceeded maximum" in outcome.error
    assert outcome.total_output_chars > 10


def test_execute_respects_retry_budget():
    attempts = {"count": 0}

    def fail_then_fail(args, ctx):
        attempts["count"] += 1
        return ToolResult(tool_name="web_search", success=False, error=f"failure {attempts['count']}")

    registry = _make_registry(_make_tool("web_search", executor=fail_then_fail, timeout_seconds=0.25))
    executor = AgentExecutor(
        registry,
        limits=ResourceLimits(max_iterations=5, max_tool_calls=10, max_execution_seconds=30, max_retries=1),
    )

    outcome = executor.execute("search the web for Paris")

    assert outcome.error is not None
    assert "Maximum retries (1) exceeded" in outcome.error
    assert attempts["count"] >= 2


def test_total_tool_calls_and_output_are_tracked_after_success():
    registry = _make_registry(_make_tool("web_search", output="A result", timeout_seconds=0.25))
    executor = AgentExecutor(registry, limits=ResourceLimits(max_iterations=3, max_execution_seconds=30))

    outcome = executor.execute("search the web for Paris")

    assert outcome.total_tool_calls == 1
    assert outcome.total_output_chars >= len("A result")
    assert outcome.success is True


def test_tool_registry_timeout_returns_timed_out_result():
    def slow_tool(args, ctx):
        time.sleep(0.5)
        return ToolResult(tool_name="slow_tool", success=True, output="late")

    registry = ToolRegistry()
    registry.register(Tool(
        name="slow_tool",
        description="slow",
        category="test",
        input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=0.05,
        executor=slow_tool,
    ))

    result = registry.execute("slow_tool", {"query": "hello"})

    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in (result.error or "").lower()


def test_tool_registry_unknown_tool_returns_error_result():
    registry = ToolRegistry()

    result = registry.execute("missing_tool", {"query": "hello"})

    assert result.success is False
    assert "Unknown tool" in (result.error or "")


def test_tool_registry_refuses_confirmation_required_by_default():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="confirm_me",
            description="needs approval",
            category="test",
            input_schema={},
            requires_confirmation=True,
            risk_level=RiskLevel.HIGH,
            timeout_seconds=1,
            executor=lambda args, ctx: ToolResult(tool_name="confirm_me", success=True, output="ok"),
        )
    )

    result = registry.execute("confirm_me", {})

    assert result.success is False
    assert result.metadata.get("requires_confirmation") is True


def test_tool_registry_runs_when_pending_override_is_used():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="confirm_me",
            description="needs approval",
            category="test",
            input_schema={},
            requires_confirmation=True,
            risk_level=RiskLevel.HIGH,
            timeout_seconds=1,
            executor=lambda args, ctx: ToolResult(tool_name="confirm_me", success=True, output="ok"),
        )
    )

    result = registry.execute("confirm_me", {}, allow_pending=True)

    assert result.success is True
    assert result.output == "ok"


def test_tool_registry_wraps_executor_exceptions():
    def bad(args, ctx):
        raise RuntimeError("boom from tests")

    registry = _make_registry(_make_tool("bad_tool", executor=bad, timeout_seconds=0.25))

    result = registry.execute("bad_tool", {})

    assert result.success is False
    assert "RuntimeError" in (result.error or "")


def test_tool_registry_uses_default_timeout_when_value_is_zero_or_negative():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="tiny_timeout",
            description="default timeout",
            category="test",
            input_schema={},
            requires_confirmation=False,
            risk_level=RiskLevel.LOW,
            timeout_seconds=0,
            executor=lambda args, ctx: ToolResult(tool_name="tiny_timeout", success=True, output="done"),
        )
    )

    result = registry.execute("tiny_timeout", {})

    assert result.success is True
    assert result.output == "done"


def test_agent_executor_uses_custom_limits_instance():
    registry = _make_registry(_make_tool("web_search", output="done"))
    limits = ResourceLimits(max_iterations=2, max_execution_seconds=9, max_tool_calls=5)
    executor = AgentExecutor(registry, limits=limits)

    assert executor.limits is limits
    assert executor.limits.max_execution_seconds == 9
    assert executor.limits.max_tool_calls == 5


def test_tool_registry_timeout_fails_gracefully_without_leaking_secrets():
    def secret_tool(args, ctx):
        raise RuntimeError("api_key=secret-value")

    registry = _make_registry(_make_tool("secret_tool", executor=secret_tool, timeout_seconds=0.25))

    result = registry.execute("secret_tool", {})

    assert result.success is False
    assert "secret-value" not in (result.error or "")
    assert "redacted" in (result.error or "").lower()


def test_executor_max_iterations_is_legacy_backwards_compatible_with_limits_object():
    registry = _make_registry(_make_tool("web_search", output="done"))
    executor = AgentExecutor(registry, max_iterations=4, limits=ResourceLimits(max_iterations=9))

    assert executor.limits.max_iterations == 9


def test_agent_executor_keeps_total_output_chars_for_large_payloads():
    payload = "z" * 250
    registry = _make_registry(_make_tool("web_search", output=payload))
    executor = AgentExecutor(registry, limits=ResourceLimits(max_iterations=3, max_execution_seconds=30))

    outcome = executor.execute("search the web for Paris")

    assert outcome.total_output_chars >= len(payload)
    assert outcome.success is True
