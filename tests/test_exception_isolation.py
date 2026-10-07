"""Regression tests for safe exception isolation across agent and API boundaries."""

from unittest.mock import patch


class TestExceptionIsolation:
    def test_agent_run_handles_memory_extraction_failure(self, tmp_db):
        from agents.agent import Agent

        agent = Agent()

        with patch("agents.agent.extract_and_store_memories", side_effect=RuntimeError("boom")):
            result = agent.run("My name is Alice", user_id=1)

        assert isinstance(result, dict)
        assert "prompt" in result
        assert result["action"] in {"chat", "memory", "error"}
        assert "boom" not in str(result.get("tool_results") or "")

    def test_tool_registry_returns_safe_tool_result_on_executor_error(self):
        from agents.tool_registry import Tool, ToolContext, ToolRegistry

        registry = ToolRegistry()

        def boom(args, context):
            raise RuntimeError("token=secret-value")

        registry.register(
            Tool(
                name="broken_tool",
                description="test",
                category="test",
                executor=boom,
            )
        )

        result = registry.execute("broken_tool", {"x": 1}, ToolContext(user_id=1))

        assert result.success is False
        assert result.timed_out is False
        assert "secret-value" not in (result.error or "")
        assert "RuntimeError" in (result.error or "")
