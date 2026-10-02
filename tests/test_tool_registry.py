"""Tests for the unified Tool Registry and its default implementations."""

import pytest
from unittest.mock import patch

from agents.tool_registry import (
    RiskLevel,
    Tool,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolRequest,
)
from agents.tool_implementations import (
    get_tool_registry,
    register_default_tools,
    reset_tool_registry,
)


# ---------------------------------------------------------------------------
# Dataclass / contract basics
# ---------------------------------------------------------------------------

class TestToolContract:
    def test_tool_result_text_prefers_observation(self):
        result = ToolResult(
            tool_name="python_exec",
            success=True,
            output="42",
            observation="<tool name='python_exec'>ok</tool>",
        )
        assert result.text == result.observation

    def test_tool_result_text_falls_back_to_output(self):
        result = ToolResult(tool_name="x", success=True, output="raw", observation="")
        assert result.text == "raw"

    def test_tool_invalid_risk_level(self):
        with pytest.raises(ValueError):
            Tool(name="bad", description="d", category="x", risk_level="nuclear")

    def test_tool_context_defaults(self):
        ctx = ToolContext()
        assert ctx.user_id is None
        assert ctx.project_id is None

    def test_tool_request_requires_name(self):
        with pytest.raises(ValueError):
            ToolRequest(name="")


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------

def _dummy_tool(name="dummy", executor=None, **kwargs):
    def _exec(args, ctx):
        return ToolResult(tool_name=name, success=True, output="ok", observation="ok")
    return Tool(
        name=name,
        description="d",
        category="x",
        requires_confirmation=kwargs.get("requires_confirmation", False),
        risk_level=kwargs.get("risk_level", RiskLevel.LOW),
        executor=executor or _exec,
    )


class TestToolRegistry:
    def test_register_and_get(self):
        r = ToolRegistry()
        tool = _dummy_tool("foo")
        r.register(tool)
        assert r.has("foo")
        assert r.get("foo").name == "foo"

    def test_get_unknown_raises(self):
        r = ToolRegistry()
        with pytest.raises(ToolError):
            r.get("nope")

    def test_unregister(self):
        r = ToolRegistry()
        r.register(_dummy_tool("a"))
        r.unregister("a")
        assert not r.has("a")

    def test_list_and_names(self):
        r = ToolRegistry()
        r.register(_dummy_tool("b"))
        r.register(_dummy_tool("a"))
        names = r.names()
        assert names == ["a", "b"]
        assert len(r.list_tools()) == 2

    def test_schema_serialisable(self):
        r = ToolRegistry()
        r.register(_dummy_tool("a"))
        schema = r.schema()
        assert isinstance(schema, list)
        assert schema[0]["name"] == "a"
        assert schema[0]["risk_level"] == RiskLevel.LOW

    def test_execute_success(self):
        r = ToolRegistry()
        r.register(_dummy_tool("ok"))
        res = r.execute("ok", {})
        assert res.success is True
        assert res.tool_name == "ok"

    def test_execute_unknown_returns_error_result(self):
        r = ToolRegistry()
        res = r.execute("missing", {})
        assert res.success is False
        assert "Unknown tool" in res.error

    def test_execute_refused_when_confirmation_required(self):
        r = ToolRegistry()
        tool = _dummy_tool("confirm_me", requires_confirmation=True,
                           risk_level=RiskLevel.HIGH)
        r.register(tool)
        res = r.execute("confirm_me", {})
        assert res.success is False
        assert res.metadata.get("requires_confirmation") is True

    def test_execute_runs_when_confirmation_overridden(self):
        r = ToolRegistry()
        r.register(_dummy_tool("confirm_me", requires_confirmation=True,
                               risk_level=RiskLevel.HIGH))
        res = r.execute("confirm_me", {}, allow_pending=True)
        assert res.success is True

    def test_execute_swallows_executor_exception(self):
        def bad(args, ctx):
            raise RuntimeError("boom")
        r = ToolRegistry()
        r.register(_dummy_tool("bad", executor=bad))
        res = r.execute("bad", {})
        assert res.success is False
        assert "RuntimeError" in res.error

    def test_execute_error_does_not_leak_secrets(self):
        def secretive(args, ctx):
            raise RuntimeError("api_key=sk-1234567890abcdef")
        r = ToolRegistry()
        r.register(_dummy_tool("leak", executor=secretive))
        res = r.execute("leak", {})
        assert "sk-1234567890abcdef" not in (res.error or "")


# ---------------------------------------------------------------------------
# Default implementations
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    def test_default_tools_registered(self):
        r = register_default_tools(ToolRegistry())
        assert set(r.names()) == {
            "python_exec", "web_search", "get_current_time",
            "rag_search", "vision", "image_gen",
        }

    def test_python_exec_safe(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("python_exec", {"code": "print(2 + 2)"})
        assert res.success is True
        assert res.output == "4"

    def test_python_exec_blocks_import_os(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("python_exec", {"code": "import os"})
        assert res.success is False
        assert "Safety validation failed" in (res.error or "")

    def test_python_exec_empty_code(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("python_exec", {"code": ""})
        assert res.success is False
        assert "No code" in res.error

    def test_get_current_time(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("get_current_time")
        assert res.success is True
        assert "Real-Time Clock" in res.observation

    def test_python_exec_timeout(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("python_exec", {
            "code": "import time\nwhile True:\n    time.sleep(1)",
            "timeout_seconds": 2,
        })
        assert res.success is False
        assert res.timed_out is True


class TestWebSearchTool:
    def test_web_search_returns_structured_result(self):
        fake = {
            "results": [
                {"title": "T", "body": "B", "link": "https://t.com"},
            ],
            "original_query": "capital of France",
            "final_query": "capital of France",
            "reformulated": False,
            "reformulation_reason": None,
            "total_found": 1,
            "returned": 1,
        }
        r = register_default_tools(ToolRegistry())
        with patch("agents.tools.web_search", return_value=fake):
            res = r.execute("web_search", {"query": "capital of France"})
        assert res.success is True
        assert "T" in res.output

    def test_web_search_no_query(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("web_search", {"query": ""})
        assert res.success is False


class TestRagSearchTool:
    def test_rag_project_scoped(self):
        r = register_default_tools(ToolRegistry())
        with patch("rag.search_project_pdf", return_value="DOC CONTENT") as mock:
            res = r.execute("rag_search", {"query": "hello"},
                            context=ToolContext(project_id=5))
        assert res.success is True
        mock.assert_called_once_with("hello", 5)
        assert "DOC CONTENT" in res.output

    def test_rag_no_user_no_project(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("rag_search", {"query": "hello"}, context=ToolContext())
        assert res.success is True
        assert "No relevant" in res.observation


class TestVisionTool:
    def test_vision_delegates(self):
        r = register_default_tools(ToolRegistry())
        with patch("vision.analyze_image", return_value="It is a cat.") as mock:
            res = r.execute("vision",
                            {"image_path": "/tmp/x.jpg",
                             "prompt": "what is this"})
        assert res.success is True
        mock.assert_called_once_with("/tmp/x.jpg", "what is this")
        assert "cat" in res.output

    def test_vision_no_path(self):
        r = register_default_tools(ToolRegistry())
        res = r.execute("vision", {})
        assert res.success is False
