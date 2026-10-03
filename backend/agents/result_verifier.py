"""Verification layer for MyGPT tool results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.result_collector import CollectedToolResult


@dataclass(frozen=True)
class VerificationResult:
    """Result of validating a collected tool result."""

    valid: bool
    tool_name: str
    reason: str = ""
    retryable: bool = False

    @property
    def verified(self) -> bool:
        return self.valid


def verify_tool_result(
    result: Optional[CollectedToolResult],
) -> VerificationResult:
    """Verify whether a collected tool result is usable."""

    if result is None:
        return VerificationResult(
            valid=False,
            tool_name="",
            reason="No tool result was provided.",
            retryable=False,
        )

    if result.timed_out or result.status == "timeout":
        return VerificationResult(
            valid=False,
            tool_name=result.tool_name,
            reason="Tool execution timed out.",
            retryable=True,
        )

    if not result.success or result.status == "error":
        return VerificationResult(
            valid=False,
            tool_name=result.tool_name,
            reason=result.error or "Tool execution failed.",
            retryable=True,
        )

    if not result.text.strip():
        return VerificationResult(
            valid=False,
            tool_name=result.tool_name,
            reason="Tool returned an empty result.",
            retryable=True,
        )

    return VerificationResult(
        valid=True,
        tool_name=result.tool_name,
        reason="Tool result is valid and usable.",
        retryable=False,
    )