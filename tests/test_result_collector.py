from agents.result_collector import (
    ResultCollector,
)

from agents.tool_registry import ToolResult


def test_success_result_is_collected():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="test_tool",
        success=True,
        output="hello",
        observation="Tool completed successfully.",
        metadata={
            "count": 1,
        },
    )

    collected = collector.collect(result)

    assert collected.tool_name == "test_tool"
    assert collected.success is True
    assert collected.status == "success"
    assert collected.output == "hello"
    assert collected.observation == "Tool completed successfully."
    assert collected.metadata["count"] == 1
    assert collected.text == "Tool completed successfully."


def test_error_result_is_collected():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="test_tool",
        success=False,
        error="Something went wrong.",
    )

    collected = collector.collect(result)

    assert collected.success is False
    assert collected.status == "error"
    assert collected.error == "Something went wrong."
    assert collected.text == "Something went wrong."


def test_timeout_result_is_collected():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="slow_tool",
        success=False,
        error="Tool timed out.",
        timed_out=True,
    )

    collected = collector.collect(result)

    assert collected.success is False
    assert collected.status == "timeout"
    assert collected.timed_out is True
    assert collected.error == "Tool timed out."


def test_output_is_used_when_observation_is_empty():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="test_tool",
        success=True,
        output="raw output",
    )

    collected = collector.collect(result)

    assert collected.text == "raw output"


def test_empty_result_text_is_safe():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="test_tool",
        success=True,
    )

    collected = collector.collect(result)

    assert collected.text == ""


def test_collect_many_preserves_order():
    collector = ResultCollector()

    results = [
        ToolResult(
            tool_name="first",
            success=True,
            output="1",
        ),
        ToolResult(
            tool_name="second",
            success=True,
            output="2",
        ),
        ToolResult(
            tool_name="third",
            success=False,
            error="failed",
        ),
    ]

    collected = collector.collect_many(results)

    assert len(collected) == 3
    assert [item.tool_name for item in collected] == [
        "first",
        "second",
        "third",
    ]


def test_latest_returns_last_result():
    collector = ResultCollector()

    collector.collect(
        ToolResult(
            tool_name="first",
            success=True,
        )
    )

    collector.collect(
        ToolResult(
            tool_name="second",
            success=True,
        )
    )

    latest = collector.latest()

    assert latest is not None
    assert latest.tool_name == "second"


def test_successful_and_failed_results():
    collector = ResultCollector()

    collector.collect(
        ToolResult(
            tool_name="success_tool",
            success=True,
        )
    )

    collector.collect(
        ToolResult(
            tool_name="error_tool",
            success=False,
            error="failed",
        )
    )

    collector.collect(
        ToolResult(
            tool_name="timeout_tool",
            success=False,
            error="timeout",
            timed_out=True,
        )
    )

    successful = collector.successful()
    failed = collector.failed()

    assert len(successful) == 1
    assert successful[0].tool_name == "success_tool"

    assert len(failed) == 2
    assert [item.tool_name for item in failed] == [
        "error_tool",
        "timeout_tool",
    ]


def test_clear_removes_collected_results():
    collector = ResultCollector()

    collector.collect(
        ToolResult(
            tool_name="test_tool",
            success=True,
        )
    )

    assert len(collector.results) == 1

    collector.clear()

    assert collector.results == []


def test_observation_has_priority_over_output():
    collector = ResultCollector()

    result = ToolResult(
        tool_name="test_tool",
        success=True,
        output="machine output",
        observation="LLM observation",
    )

    collected = collector.collect(result)

    assert collected.text == "LLM observation"