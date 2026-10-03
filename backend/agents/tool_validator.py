"""Validation helpers for MyGPT ToolRegistry requests."""

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.tool_registry import ToolError, ToolRegistry


def validate_tool_request(
    registry: ToolRegistry,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Validate a tool request before execution.

    Returns:
        (True, None) when the tool exists and arguments are acceptable.
        (False, error_message) when validation fails.
    """

    # Validate tool name
    if not tool_name or not isinstance(tool_name, str):
        return False, "Invalid tool name."

    # Look up tool safely
    try:
        tool = registry.get(tool_name)
    except ToolError:
        return False, f"Unknown tool: {tool_name}"

    # Normalize None arguments to empty dictionary
    if args is None:
        args = {}

    # Arguments must be a dictionary
    if not isinstance(args, dict):
        return False, "Tool arguments must be a dictionary."

    # Tool uses input_schema, not schema
    schema = tool.input_schema or {}

    # Required arguments
    required = schema.get("required", [])

    for field in required:
        if field not in args or args[field] is None:
            return False, f"Missing required argument: {field}"

    # Property definitions
    properties = schema.get("properties", {})

    for field, value in args.items():
        # Ignore arguments that are not explicitly defined
        if field not in properties:
            continue

        expected_type = properties[field].get("type")

        if expected_type == "string":
            if not isinstance(value, str):
                return False, f"Argument '{field}' must be a string."

        elif expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return False, f"Argument '{field}' must be an integer."

        elif expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False, f"Argument '{field}' must be a number."

        elif expected_type == "boolean":
            if not isinstance(value, bool):
                return False, f"Argument '{field}' must be a boolean."

        elif expected_type == "object":
            if not isinstance(value, dict):
                return False, f"Argument '{field}' must be an object."

        elif expected_type == "array":
            if not isinstance(value, list):
                return False, f"Argument '{field}' must be an array."

    return True, None