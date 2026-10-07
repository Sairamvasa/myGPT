"""Unified Tool Registry for the MyGPT autonomous agent.

This module defines the *contracts* only:

  - ``Tool``        — declarative metadata for a tool
                       (name, description, category, input_schema,
                       requires_confirmation, risk_level, timeout_seconds,
                       executor).
  - ``ToolResult``  — structured result contract returned by every tool
                       (tool_name, success, output, error, observation,
                       metadata, timed_out).
  - ``ToolContext`` — per-request execution context (user_id, chat_id,
                       project_id, trace_id) used for isolation.
  - ``ToolError``   — raised by the registry for unknown / refused tools.
  - ``RiskLevel``   — low / medium / high classification.
  - ``ToolRegistry``— register / get / list / execute with confirmation
                       and timeout enforcement.

Concrete tool implementations live in ``tool_implementations.py`` and wrap
the existing, battle-tested functions in ``agents.tools`` / ``rag`` /
``vision`` so no behaviour is duplicated or weakened.
"""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("MyGPT.ToolRegistry")


class RiskLevel:
    """Risk classification for a tool.

    LOW    — read-only, no side effects (e.g. current time).
    MEDIUM — network/external calls (e.g. web search).
    HIGH   — code execution / writes / system access (e.g. python_exec).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    VALUES = frozenset({LOW, MEDIUM, HIGH})


class ToolError(Exception):
    """Raised by the registry when a tool is unknown or refused."""

    def __init__(self, message: str, tool_name: Optional[str] = None):
        super().__init__(message)
        self.tool_name = tool_name


@dataclass
class ToolContext:
    """Per-request execution context for tool isolation scoping."""

    user_id: Optional[int] = None
    chat_id: Optional[int] = None
    project_id: Optional[int] = None
    trace_id: Optional[str] = None


# An executor takes (args, context) and returns a ToolResult.
ToolExecutor = Callable[[Dict[str, Any], ToolContext], "ToolResult"]


@dataclass
class Tool:
    """Declarative descriptor for a tool the agent may call."""

    name: str
    description: str
    category: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    risk_level: str = RiskLevel.LOW
    timeout_seconds: int = 30
    executor: Optional[ToolExecutor] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.risk_level not in RiskLevel.VALUES:
            raise ValueError(f"Invalid risk_level: {self.risk_level!r}")

    @property
    def is_safe(self) -> bool:
        return self.risk_level != RiskLevel.HIGH


@dataclass
class ToolResult:
    """Structured result returned by every tool execution.

    ``output``     — the primary machine-readable return value.
    ``observation``— human/LLM-readable summary fed back into the prompt.
    ``metadata``   — diagnostic dict (e.g. exit_code, source counts).
    """

    tool_name: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    observation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False

    @property
    def text(self) -> str:
        """The string that gets injected into the agent's prompt scratchpad."""
        return self.observation if self.observation else self.output


@dataclass
class ToolRequest:
    """A single tool call requested by the planner/LLM."""

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ToolRequest name is required")


class ToolRegistry:
    """Registers tools and executes them in a controlled way with timeout enforcement."""

    # Shared thread pool for timeout enforcement across all registry instances
    _executor_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    @classmethod
    def _get_pool(cls) -> concurrent.futures.ThreadPoolExecutor:
        """Get or create the shared thread pool for timeout enforcement."""
        if cls._executor_pool is None:
            cls._executor_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=8, thread_name_prefix="mygpt-tool-"
            )
        return cls._executor_pool

    @classmethod
    def shutdown_pool(cls, wait: bool = True) -> None:
        """Shutdown the shared thread pool (for testing/cleanup)."""
        if cls._executor_pool is not None:
            cls._executor_pool.shutdown(wait=wait)
            cls._executor_pool = None

    # -- registration --------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register (or replace) a tool."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (risk=%s, confirm=%s)",
                     tool.name, tool.risk_level, tool.requires_confirmation)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    # -- lookup --------------------------------------------------------------

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError(f"Unknown tool: {name!r}", tool_name=name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return sorted(self._tools.keys())

    def schema(self) -> List[Dict[str, Any]]:
        """Return JSON-serialisable metadata for every registered tool."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "input_schema": t.input_schema,
                "requires_confirmation": t.requires_confirmation,
                "risk_level": t.risk_level,
                "timeout_seconds": t.timeout_seconds,
            }
            for t in self._tools.values()
        ]

    # -- execution -----------------------------------------------------------

    def execute(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[ToolContext] = None,
        allow_pending: bool = False,
    ) -> ToolResult:
        """Execute a registered tool with timeout enforcement.

        ``allow_pending`` — when False (default) tools that require
        confirmation return a refused result instead of running.  Set it
        True when the caller has already obtained user confirmation.
        """
        arguments = arguments or {}
        context = context or ToolContext()

        try:
            tool = self.get(name)
        except ToolError:
            # Unknown tool — degrade gracefully so the agent loop can
            # recover (Phase 3: error recovery) instead of crashing.
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"Unknown tool: {name!r}",
                observation=(
                    f"[TOOL_ERROR] The tool '{name}' is not available. "
                    "It was not executed."
                ),
                metadata={"error_type": "unknown_tool"},
            )

        if tool.requires_confirmation and not allow_pending:
            logger.warning(
                "Tool %s execution refused: requires confirmation", name,
            )
            return ToolResult(
                tool_name=name,
                success=False,
                error="Tool requires explicit user confirmation before it can run.",
                observation=(
                    f"[TOOL_REQUIRES_CONFIRMATION] The tool '{name}' ("
                    f"risk={tool.risk_level}) needs your approval before "
                    "execution. Re-issue with confirmation once approved."
                ),
                metadata={"requires_confirmation": True, "risk_level": tool.risk_level},
            )

        if tool.executor is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error="Tool has no registered executor.",
                observation=f"[TOOL_ERROR] '{name}' is not executable on this server.",
            )

        timeout = tool.timeout_seconds
        if timeout <= 0:
            timeout = 30

        logger.info(
            "Executing tool %s (timeout=%ss, user_id=%s, project_id=%s)",
            name,
            timeout,
            context.user_id,
            context.project_id,
        )

        # Execute with centralized timeout enforcement
        pool = self._get_pool()
        future = pool.submit(tool.executor, arguments, context)

        try:
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            # Cancel the future to prevent it from continuing in background
            future.cancel()
            logger.warning("Tool %s timed out after %ss (enforced by registry)", name, timeout)
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' timed out after {timeout}s.",
                timed_out=True,
                observation=(
                    f"[TOOL_ERROR] '{name}' timed out after {timeout} seconds."
                ),
                metadata={"timed_out": True, "timeout_enforced_by": "registry"},
            )
        except ToolError as exc:
            return ToolResult(
                tool_name=name,
                success=False,
                error=str(exc),
                observation=f"[TOOL_ERROR] {exc}",
                metadata={"error_type": "ToolError"},
            )
        except RecursionError:
            return ToolResult(
                tool_name=name,
                success=False,
                error="Tool hit a recursion limit.",
                observation=f"[TOOL_ERROR] '{name}' exceeded recursion depth.",
                metadata={"error_type": "RecursionError"},
            )
        except Exception as exc:  # noqa: BLE001 - registry is the safety boundary
            safe = _sanitize_error(exc)
            logger.exception("Tool %s raised: %s", name, safe)
            return ToolResult(
                tool_name=name,
                success=False,
                error=safe,
                observation=f"[TOOL_ERROR] '{name}' failed unexpectedly.",
                metadata={"error_type": type(exc).__name__},
            )

        if not isinstance(result, ToolResult):
            raise ToolError(
                f"Executor for '{name}' returned {type(result).__name__}, "
                "expected ToolResult",
                tool_name=name,
            )

        result.tool_name = result.tool_name or name
        return result


def _sanitize_error(exc: Exception) -> str:
    """Return an error string that never leaks secrets or huge tracebacks."""
    msg = str(exc).strip()
    if not msg:
        msg = type(exc).__name__
    # Avoid echoing API keys / tokens that may attach to exceptions.
    for secret in ("api_key", "token", "secret", "password", "authorization"):
        if secret in msg.lower():
            return f"{type(exc).__name__}: [redacted]"
    # Bound length.
    if len(msg) > 300:
        msg = msg[:300] + "...[truncated]"
    return f"{type(exc).__name__}: {msg}"