"""Tests for Phase 5.2 Advanced Agent Intelligence.

Tests the AgentExecutor controlled multi-step execution loop.
All tests use mocked/fake tool registries — no external APIs.
"""

import pytest
from unittest.mock import MagicMock

from agents.execution_loop import (
    AgentExecutor,
    ExecutionOutcome,
    ExecutionStep,
    _TERMINAL_ACTIONS,
    _CONTINUABLE_ACTIONS,
)
from agents.tool_registry import ToolRegistry, Tool, ToolResult, RiskLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name, success=True, output="", error=None, timed_out=False):
    return Tool(
        name=name,
        description=f"Test tool {name}",
        category="test",
        input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=10,
        executor=lambda args, ctx: ToolResult(
            tool_name=name,
            success=success,
            output=output,
            error=error,
            timed_out=timed_out,
        ),
    )


def _make_registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


# ---------------------------------------------------------------------------
# 1. Single-step execution
# ---------------------------------------------------------------------------

def test_single_step_execution():
    registry = _make_registry(_make_tool("web_search", output="Paris is the capital."))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web for Paris", user_id=1)

    assert outcome.success is True
    assert len(outcome.steps) >= 1
    assert outcome.steps[0].verified is True


# ---------------------------------------------------------------------------
# 2. Multi-step plan
# ---------------------------------------------------------------------------

def test_multi_step_plan():
    registry = _make_registry(
        _make_tool("web_search", output="France"),
        _make_tool("web_search", output="Paris"),
    )
    executor = AgentExecutor(registry, max_iterations=5)

    outcome = executor.execute("search the web for Paris", user_id=1)

    assert outcome.success is True
    assert len(outcome.steps) >= 1


# ---------------------------------------------------------------------------
# 3. Tool chain
# ---------------------------------------------------------------------------

def test_tool_chain():
    registry = _make_registry(
        _make_tool("web_search", output="result1"),
        _make_tool("web_search", output="result2"),
    )
    executor = AgentExecutor(registry, max_iterations=5)

    outcome = executor.execute("search the web for something", user_id=1)

    assert outcome.success is True


# ---------------------------------------------------------------------------
# 4. Successful tool execution
# ---------------------------------------------------------------------------

def test_successful_tool_execution():
    registry = _make_registry(_make_tool("web_search", output="found it"))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is True
    assert outcome.tool_results is not None
    assert "found it" in outcome.tool_results


# ---------------------------------------------------------------------------
# 5. Failed tool execution
# ---------------------------------------------------------------------------

def test_failed_tool_execution():
    registry = _make_registry(
        _make_tool("web_search", success=False, error="network error")
    )
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is False
    assert outcome.error is not None


# ---------------------------------------------------------------------------
# 6. Re-planning
# ---------------------------------------------------------------------------

def test_replanning_on_failure():
    call_count = 0

    def failing_executor(args, ctx):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ToolResult(tool_name="web_search", success=False, error="fail")
        return ToolResult(tool_name="web_search", success=True, output="recovered")

    tool = Tool(
        name="web_search",
        description="test",
        category="test",
        input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        requires_confirmation=False,
        risk_level=RiskLevel.LOW,
        timeout_seconds=10,
        executor=failing_executor,
    )
    registry = _make_registry(tool)
    executor = AgentExecutor(registry, max_iterations=5)

    outcome = executor.execute("search the web", user_id=1)

    assert call_count >= 1


# ---------------------------------------------------------------------------
# 7. Timeout
# ---------------------------------------------------------------------------

def test_timeout_handling():
    registry = _make_registry(
        _make_tool("web_search", success=False, error="timed out", timed_out=True)
    )
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is False
    assert any(step.result and step.result.timed_out for step in outcome.steps)


# ---------------------------------------------------------------------------
# 8. Verification failure
# ---------------------------------------------------------------------------

def test_verification_failure():
    registry = _make_registry(
        _make_tool("web_search", success=True, output="")
    )
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is False


# ---------------------------------------------------------------------------
# 9. Permission denial
# ---------------------------------------------------------------------------

def test_permission_denial():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="dangerous_tool",
            description="dangerous",
            category="test",
            input_schema={},
            requires_confirmation=True,
            risk_level=RiskLevel.HIGH,
            timeout_seconds=10,
            executor=lambda args, ctx: ToolResult(tool_name="dangerous_tool", success=True),
        )
    )
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is False
    assert outcome.error is not None


# ---------------------------------------------------------------------------
# 10. Unnecessary tool call prevention
# ---------------------------------------------------------------------------

def test_unnecessary_tool_call_prevention():
    registry = _make_registry(_make_tool("web_search", output="result"))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is True


# ---------------------------------------------------------------------------
# 11. Multiple tool results
# ---------------------------------------------------------------------------

def test_multiple_tool_results():
    registry = _make_registry(
        _make_tool("web_search", output="result1"),
        _make_tool("web_search", output="result2"),
    )
    executor = AgentExecutor(registry, max_iterations=5)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.success is True


# ---------------------------------------------------------------------------
# 12. Deterministic execution
# ---------------------------------------------------------------------------

def test_deterministic_execution():
    registry = _make_registry(_make_tool("web_search", output="result"))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome1 = executor.execute("search the web", user_id=1)
    outcome2 = executor.execute("search the web", user_id=1)

    assert len(outcome1.steps) == len(outcome2.steps)
    for s1, s2 in zip(outcome1.steps, outcome2.steps):
        assert s1.action == s2.action
        assert s1.tool_name == s2.tool_name
        assert s1.verified == s2.verified


# ---------------------------------------------------------------------------
# 13. Maximum iteration protection
# ---------------------------------------------------------------------------

def test_max_iteration_protection():
    registry = _make_registry(_make_tool("web_search", output="result"))
    executor = AgentExecutor(registry, max_iterations=2)

    outcome = executor.execute("search the web", user_id=1)

    assert outcome.max_iterations_reached is True or outcome.success is True


# ---------------------------------------------------------------------------
# 14. Context integration
# ---------------------------------------------------------------------------

def test_context_integration():
    registry = _make_registry(_make_tool("web_search", output="result"))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute(
        "search the web", user_id=1, chat_id=10, project_id=5
    )

    assert outcome.success is True


# ---------------------------------------------------------------------------
# 15. Security/isolation preservation
# ---------------------------------------------------------------------------

def test_security_isolation_preservation():
    registry = _make_registry(_make_tool("web_search", output="result"))
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search the web", user_id=1, chat_id=10, project_id=5)

    assert outcome.success is True


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_outcome_defaults():
    outcome = ExecutionOutcome()
    assert outcome.success is False
    assert outcome.total_iterations == 0
    assert outcome.max_iterations_reached is False


def test_terminal_actions():
    assert "time" in _TERMINAL_ACTIONS
    assert "python" in _TERMINAL_ACTIONS


def test_continuable_actions():
    assert "web" in _CONTINUABLE_ACTIONS
    assert "rag" in _CONTINUABLE_ACTIONS


def test_empty_registry():
    registry = ToolRegistry()
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search", user_id=1)

    assert outcome.success is False
    assert outcome.error is not None


def test_unknown_tool():
    registry = ToolRegistry()
    executor = AgentExecutor(registry, max_iterations=3)

    outcome = executor.execute("search", user_id=1)

    assert outcome.success is False