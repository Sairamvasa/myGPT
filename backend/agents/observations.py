"""ToolResult -> LLM observation formatting for MyGPT."""

from __future__ import annotations

from typing import Any, Dict

from agents.tool_registry import ToolResult


def tool_result_to_observation(result: ToolResult) -> str:
    """
    Convert a ToolResult into a stable, LLM-facing observation.

    The registry remains generic; this adapter owns presentation for
    the agent/prompt layer.
    """

    status = "success" if result.success else "error"

    lines = [
        f"Tool: {result.tool_name}",
        f"Status: {status}",
    ]

    if result.timed_out:
        lines.append("Timed out: yes")

    if result.error:
        lines.append(f"Error: {result.error}")

    observation = result.observation or result.output

    if observation:
        lines.extend([
            "",
            "Observation:",
            str(observation),
        ])

    if result.metadata:
        safe_metadata = _format_metadata(result.metadata)

        if safe_metadata:
            lines.extend([
                "",
                "Metadata:",
                safe_metadata,
            ])

    return "\n".join(lines)


def _format_metadata(metadata: Dict[str, Any]) -> str:
    """Format diagnostic metadata without exposing huge values."""

    lines = []

    for key, value in metadata.items():
        if value is None:
            continue

        text = str(value)

        if len(text) > 500:
            text = text[:500] + "...[truncated]"

        lines.append(f"- {key}: {text}")

    return "\n".join(lines)