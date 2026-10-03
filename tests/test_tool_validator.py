from agents.tool_registry import (
    Tool,
    ToolRegistry,
)

from agents.tool_validator import validate_tool_request


def make_registry():
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="test_tool",
            description="Test tool",
            category="test",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                    },
                    "limit": {
                        "type": "integer",
                    },
                },
                "required": ["query"],
            },
            executor=lambda args, context: None,
        )
    )

    return registry


def test_valid_tool_request():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "test_tool",
        {
            "query": "hello",
            "limit": 5,
        },
    )

    assert valid is True
    assert error is None


def test_unknown_tool_rejected():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "unknown_tool",
        {},
    )

    assert valid is False
    assert "Unknown tool" in error


def test_missing_required_argument_rejected():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "test_tool",
        {},
    )

    assert valid is False
    assert "query" in error


def test_wrong_string_type_rejected():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "test_tool",
        {
            "query": 123,
        },
    )

    assert valid is False
    assert "string" in error


def test_wrong_integer_type_rejected():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "test_tool",
        {
            "query": "hello",
            "limit": "five",
        },
    )

    assert valid is False
    assert "integer" in error


def test_none_arguments_are_allowed_when_no_required_fields():
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="no_args_tool",
            description="No args tool",
            category="test",
            input_schema={
                "type": "object",
                "properties": {},
            },
            executor=lambda args, context: None,
        )
    )

    valid, error = validate_tool_request(
        registry,
        "no_args_tool",
        None,
    )

    assert valid is True
    assert error is None


def test_non_dict_arguments_rejected():
    registry = make_registry()

    valid, error = validate_tool_request(
        registry,
        "test_tool",
        ["invalid"],
    )

    assert valid is False
    assert "dictionary" in error