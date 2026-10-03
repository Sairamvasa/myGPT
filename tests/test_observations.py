from agents.observations import tool_result_to_observation
from agents.tool_registry import ToolResult


def test_success_observation():
    result = ToolResult(
        tool_name="web_search",
        success=True,
        output="raw output",
        observation="Search returned 5 results.",
        metadata={
            "returned": 5,
            "query": "latest NVIDIA news",
        },
    )

    text = tool_result_to_observation(result)

    assert "Tool: web_search" in text
    assert "Status: success" in text
    assert "Search returned 5 results." in text
    assert "returned: 5" in text


def test_output_used_when_observation_missing():
    result = ToolResult(
        tool_name="calculator",
        success=True,
        output="42",
    )

    text = tool_result_to_observation(result)

    assert "Tool: calculator" in text
    assert "Status: success" in text
    assert "42" in text


def test_error_observation():
    result = ToolResult(
        tool_name="python_exec",
        success=False,
        error="Execution failed",
        observation="[TOOL_ERROR] Python execution failed.",
    )

    text = tool_result_to_observation(result)

    assert "Tool: python_exec" in text
    assert "Status: error" in text
    assert "Execution failed" in text
    assert "[TOOL_ERROR]" in text


def test_timeout_observation():
    result = ToolResult(
        tool_name="web_search",
        success=False,
        timed_out=True,
        error="Timed out",
    )

    text = tool_result_to_observation(result)

    assert "Timed out: yes" in text


def test_metadata_is_truncated():
    result = ToolResult(
        tool_name="test",
        success=True,
        metadata={"large": "x" * 1000},
    )

    text = tool_result_to_observation(result)

    assert "...[truncated]" in text