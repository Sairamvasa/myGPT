from agents.result_collector import CollectedToolResult
from agents.result_verifier import verify_tool_result


def test_none_result_is_invalid():
    result = verify_tool_result(None)

    assert result.valid is False
    assert result.verified is False
    assert result.retryable is False


def test_successful_result_is_valid():
    collected = CollectedToolResult(
        tool_name="python_exec",
        success=True,
        status="success",
        output="42",
    )

    result = verify_tool_result(collected)

    assert result.valid is True
    assert result.verified is True
    assert result.retryable is False


def test_observation_can_make_result_valid():
    collected = CollectedToolResult(
        tool_name="web_search",
        success=True,
        status="success",
        observation="Search result found.",
    )

    result = verify_tool_result(collected)

    assert result.valid is True


def test_failed_result_is_invalid():
    collected = CollectedToolResult(
        tool_name="web_search",
        success=False,
        status="error",
        error="Search failed.",
    )

    result = verify_tool_result(collected)

    assert result.valid is False
    assert result.retryable is True
    assert "Search failed." in result.reason


def test_timeout_result_is_invalid():
    collected = CollectedToolResult(
        tool_name="python_exec",
        success=False,
        status="timeout",
        timed_out=True,
    )

    result = verify_tool_result(collected)

    assert result.valid is False
    assert result.retryable is True
    assert "timed out" in result.reason.lower()


def test_empty_result_is_invalid():
    collected = CollectedToolResult(
        tool_name="rag_search",
        success=True,
        status="success",
        output="",
        observation="",
    )

    result = verify_tool_result(collected)

    assert result.valid is False
    assert result.retryable is True


def test_observation_has_priority():
    collected = CollectedToolResult(
        tool_name="rag_search",
        success=True,
        status="success",
        output="",
        observation="Document context found.",
    )

    result = verify_tool_result(collected)

    assert result.valid is True


def test_error_without_message_gets_default_reason():
    collected = CollectedToolResult(
        tool_name="vision",
        success=False,
        status="error",
    )

    result = verify_tool_result(collected)

    assert result.valid is False
    assert result.retryable is True
    assert result.reason == "Tool execution failed."