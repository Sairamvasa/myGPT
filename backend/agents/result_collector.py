"""Standardized tool result collection for MyGPT orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agents.tool_registry import ToolResult


@dataclass(frozen=True)
class CollectedToolResult:
    """Normalized representation of a completed tool execution."""

    tool_name: str
    success: bool
    status: str
    output: str = ""
    error: Optional[str] = None
    observation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False

    @property
    def text(self) -> str:
        """Return the best human/LLM-readable result text."""
        if self.observation:
            return self.observation

        if self.output:
            return self.output

        if self.error:
            return self.error

        return ""


@dataclass
class ResultCollector:
    """Collect and normalize ToolResult objects from tool execution."""

    results: List[CollectedToolResult] = field(default_factory=list)

    def collect(self, result: ToolResult) -> CollectedToolResult:
        """Normalize and store one ToolResult."""

        if result.timed_out:
            status = "timeout"
        elif result.success:
            status = "success"
        else:
            status = "error"

        collected = CollectedToolResult(
            tool_name=result.tool_name,
            success=result.success,
            status=status,
            output=result.output or "",
            error=result.error,
            observation=result.observation or "",
            metadata=dict(result.metadata or {}),
            timed_out=result.timed_out,
        )

        self.results.append(collected)

        return collected

    def collect_many(
        self,
        results: List[ToolResult],
    ) -> List[CollectedToolResult]:
        """Collect multiple tool results in execution order."""

        return [self.collect(result) for result in results]

    def latest(self) -> Optional[CollectedToolResult]:
        """Return the most recently collected result."""

        if not self.results:
            return None

        return self.results[-1]

    def successful(self) -> List[CollectedToolResult]:
        """Return only successful results."""

        return [
            result
            for result in self.results
            if result.success
        ]

    def failed(self) -> List[CollectedToolResult]:
        """Return error or timeout results."""

        return [
            result
            for result in self.results
            if not result.success
        ]

    def clear(self) -> None:
        """Clear all collected results."""

        self.results.clear()