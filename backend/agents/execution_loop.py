"""Controlled multi-step execution loop for the MyGPT agent.

Reuses all existing components without duplicating them:
- planner.decide() for action selection
- tool_selector.select_tool() for tool mapping
- tool_validator.validate_tool_request() for validation
- tool_permissions.evaluate_tool_permission() for permission checks
- tool_registry.execute() for execution
- result_collector.ResultCollector() for result collection
- observations.tool_result_to_observation() for observation formatting
- result_verifier.verify_tool_result() for verification

The loop is conservative by default (max_iterations=5) and never
executes after DENY, without required confirmation, or past the
iteration limit.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from agents.planner import (
    decide,
    ACTION_CHAT,
    ACTION_PYTHON,
    ACTION_TIME,
    ACTION_WEB,
    ACTION_RAG,
    ACTION_CODE,
    ACTION_CODE_EXPLANATION,
    ACTION_CURRENT_INFO,
    ACTION_WEB_RESEARCH,
    ACTION_MEMORY,
    ACTION_IMAGE_GEN,
    ACTION_VISION,
    ACTION_MATH,
    ACTION_CREATIVE,
    ACTION_GENERAL_KNOWLEDGE,
)
from agents.tool_selector import select_tool
from agents.tool_validator import validate_tool_request
from agents.tool_permissions import evaluate_tool_permission, PermissionDecision
from agents.result_collector import ResultCollector
from agents.observations import tool_result_to_observation
from agents.result_verifier import verify_tool_result
from agents.tool_registry import ToolRegistry, ToolContext, ToolResult

logger = logging.getLogger("MyGPT.ExecutionLoop")

# Actions that are terminal after a single successful execution.
_TERMINAL_ACTIONS = {
    ACTION_TIME,
    ACTION_PYTHON,
    ACTION_CODE,
    ACTION_CODE_EXPLANATION,
    ACTION_IMAGE_GEN,
    ACTION_VISION,
    ACTION_MATH,
    ACTION_CREATIVE,
    ACTION_GENERAL_KNOWLEDGE,
}

# Actions where success does NOT automatically terminate — the loop
# may continue if the planner decides more work is needed.
_CONTINUABLE_ACTIONS = {
    ACTION_WEB,
    ACTION_CURRENT_INFO,
    ACTION_WEB_RESEARCH,
    ACTION_RAG,
    ACTION_MEMORY,
}


@dataclass(frozen=True)
class ExecutionStep:
    iteration: int
    action: str
    tool_name: Optional[str]
    result: Optional[ToolResult]
    observation: str
    verified: bool
    error: Optional[str] = None


@dataclass
class ExecutionOutcome:
    steps: list[ExecutionStep] = field(default_factory=list)
    success: bool = False
    answer: Optional[str] = None
    final_action: Optional[str] = None
    tool_results: Optional[str] = None
    error: Optional[str] = None
    max_iterations_reached: bool = False
    total_iterations: int = 0
    # New fields for timeout/resource tracking
    deadline_exceeded: bool = False
    max_tool_calls_exceeded: bool = False
    total_tool_calls: int = 0
    total_output_chars: int = 0


class ResourceLimits:
    """Configurable resource limits for agent execution."""

    def __init__(
        self,
        max_iterations: int = 5,
        max_tool_calls: int = 10,
        max_total_output_chars: int = 256_000,
        max_execution_seconds: int = 120,
        max_retries: int = 2,
    ):
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.max_total_output_chars = max_total_output_chars
        self.max_execution_seconds = max_execution_seconds
        self.max_retries = max_retries


class AgentExecutor:
    """Controlled multi-step execution loop for the MyGPT agent.

    Parameters
    ----------
    registry:
        ToolRegistry used for tool lookup and execution.
    limits:
        ResourceLimits instance configuring all bounds. Defaults are
        conservative — enough for multi-step tasks while preventing
        runaway loops and resource exhaustion.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        limits: Optional[ResourceLimits] = None,
        max_iterations: Optional[int] = None,
    ):
        """Initialize the executor.

        Parameters
        ----------
        registry:
            ToolRegistry used for tool lookup and execution.
        limits:
            ResourceLimits instance configuring all bounds. Defaults are
            conservative — enough for multi-step tasks while preventing
            runaway loops and resource exhaustion.
        max_iterations:
            Deprecated. If provided without ``limits``, creates a
            ResourceLimits with this max_iterations value.
        """
        if limits is None and max_iterations is not None:
            limits = ResourceLimits(max_iterations=max_iterations)
        self.registry = registry
        self.limits = limits or ResourceLimits()
        self.collector = ResultCollector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        message: str,
        *,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> ExecutionOutcome:
        """Run the controlled execution loop with resource limits.

        Returns an ExecutionOutcome with all steps, the final answer,
        and any error information.
        """
        outcome = ExecutionOutcome()
        tool_context = ToolContext(
            user_id=user_id,
            chat_id=chat_id,
            project_id=project_id,
        )
        current_message = message

        # Overall deadline enforcement
        start_time = time.monotonic()
        deadline = start_time + self.limits.max_execution_seconds

        retry_count = 0

        for iteration in range(self.limits.max_iterations):
            # Check overall deadline before each iteration
            if time.monotonic() > deadline:
                outcome.deadline_exceeded = True
                outcome.error = (
                    f"Agent execution exceeded maximum time of "
                    f"{self.limits.max_execution_seconds}s"
                )
                logger.warning(
                    "Execution deadline exceeded for user_id=%s (iterations=%d, "
                    "tool_calls=%d)",
                    user_id,
                    outcome.total_iterations,
                    outcome.total_tool_calls,
                )
                break

            outcome.total_iterations = iteration + 1

            # 1. Plan — decide next action
            action = decide(current_message)

            # 2. Select tool
            tool_name = select_tool(action)
            if tool_name is None:
                step = ExecutionStep(
                    iteration=iteration,
                    action=action,
                    tool_name=None,
                    result=None,
                    observation="",
                    verified=False,
                    error=f"No tool selected for action: {action}",
                )
                outcome.steps.append(step)
                outcome.error = step.error
                outcome.final_action = action
                break

            # 3. Build tool arguments
            tool_args = self._build_tool_args(action, current_message)

            # 4. Validate
            valid, validation_error = validate_tool_request(
                self.registry, tool_name, tool_args
            )
            if not valid:
                step = ExecutionStep(
                    iteration=iteration,
                    action=action,
                    tool_name=tool_name,
                    result=None,
                    observation="",
                    verified=False,
                    error=f"Validation failed: {validation_error}",
                )
                outcome.steps.append(step)
                outcome.error = step.error
                outcome.final_action = action
                break

            # 5. Permission check
            permission = evaluate_tool_permission(
                self.registry, tool_name, user_confirmed=False
            )
            if permission.decision == PermissionDecision.DENY:
                step = ExecutionStep(
                    iteration=iteration,
                    action=action,
                    tool_name=tool_name,
                    result=None,
                    observation="",
                    verified=False,
                    error=f"Permission denied: {permission.reason}",
                )
                outcome.steps.append(step)
                outcome.error = step.error
                outcome.final_action = action
                break
            if permission.decision == PermissionDecision.CONFIRM:
                step = ExecutionStep(
                    iteration=iteration,
                    action=action,
                    tool_name=tool_name,
                    result=None,
                    observation="",
                    verified=False,
                    error=f"Requires confirmation: {permission.reason}",
                )
                outcome.steps.append(step)
                outcome.error = step.error
                outcome.final_action = action
                break

            # Check tool call budget before execution
            if outcome.total_tool_calls >= self.limits.max_tool_calls:
                outcome.max_tool_calls_exceeded = True
                outcome.error = (
                    f"Maximum tool calls ({self.limits.max_tool_calls}) exceeded"
                )
                logger.warning(
                    "Max tool calls exceeded for user_id=%s (calls=%d)",
                    user_id,
                    outcome.total_tool_calls,
                )
                break

            # 6. Execute
            result = self.registry.execute(tool_name, tool_args, tool_context)

            outcome.total_tool_calls += 1

            # Track output size
            if result.output:
                outcome.total_output_chars += len(result.output)
            if result.observation:
                outcome.total_output_chars += len(result.observation)

            # Check output size limit
            if outcome.total_output_chars > self.limits.max_total_output_chars:
                outcome.error = (
                    f"Accumulated tool output exceeded maximum of "
                    f"{self.limits.max_total_output_chars} characters"
                )
                logger.warning(
                    "Output size limit exceeded for user_id=%s (chars=%d)",
                    user_id,
                    outcome.total_output_chars,
                )
                break

            # 7. Collect
            collected = self.collector.collect(result)

            # 8. Observe
            observation = tool_result_to_observation(result)

            # 9. Verify
            verification = verify_tool_result(collected)

            step = ExecutionStep(
                iteration=iteration,
                action=action,
                tool_name=tool_name,
                result=result,
                observation=observation,
                verified=verification.valid,
                error=None if verification.valid else verification.reason,
            )
            outcome.steps.append(step)

            # 10. Decide: continue, finalize, or re-plan
            if verification.valid:
                outcome.success = True
                outcome.final_action = action
                if result.success and result.output:
                    outcome.tool_results = observation
                # Terminal actions stop after success
                if action in _TERMINAL_ACTIONS:
                    outcome.answer = result.output or result.observation
                    break
                # Controllable actions may continue
                if action in _CONTINUABLE_ACTIONS:
                    if result.success and result.output:
                        # Have useful result — stop unless planner says more
                        break
                    # No output but succeeded — continue or stop
                    break
                # Default: stop after one successful non-terminal action
                break
            else:
                # Verification failed
                outcome.success = False
                outcome.error = verification.reason
                if not verification.retryable:
                    break
                # Check retry budget
                if retry_count >= self.limits.max_retries:
                    outcome.error = (
                        f"Maximum retries ({self.limits.max_retries}) exceeded: "
                        f"{verification.reason}"
                    )
                    logger.warning(
                        "Max retries exceeded for user_id=%s (retries=%d)",
                        user_id,
                        retry_count,
                    )
                    break
                retry_count += 1
                # Re-plan: append failure context so planner can adapt
                current_message = (
                    f"{message}\n\nPrevious attempt failed: {verification.reason}\n"
                    f"Try a different approach."
                )
                logger.info(
                    "Iteration %d: verification failed for %s, re-planning "
                    "(retry %d/%d)",
                    iteration,
                    tool_name,
                    retry_count,
                    self.limits.max_retries,
                )
                continue

        if outcome.total_iterations >= self.limits.max_iterations:
            outcome.max_iterations_reached = True

        # Log execution summary
        elapsed = time.monotonic() - start_time
        logger.info(
            "Execution complete user_id=%s iterations=%d tool_calls=%d "
            "output_chars=%d elapsed=%.2fs success=%s deadline_exceeded=%s",
            user_id,
            outcome.total_iterations,
            outcome.total_tool_calls,
            outcome.total_output_chars,
            elapsed,
            outcome.success,
            outcome.deadline_exceeded,
        )

        return outcome

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_tool_args(self, action: str, message: str) -> dict:
        if action == ACTION_PYTHON:
            code = self._extract_python_code(message)
            if code is None:
                return {}
            return {"code": code}
        if action in (ACTION_WEB, ACTION_RAG, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH):
            return {"query": message}
        if action == ACTION_MEMORY:
            return {"query": message}
        return {}

    def _extract_python_code(self, message: str) -> Optional[str]:
        code_match = re.search(
            r"```(?:python)?\s*([\s\S]*?)```",
            message,
            re.IGNORECASE,
        )
        if code_match:
            return code_match.group(1).strip()
        math_match = re.search(
            r"(?:calculate|compute|solve|eval|what is)\s+([0-9+\-*/^().\s%]+)",
            message,
            re.IGNORECASE,
        )
        if math_match:
            expr = math_match.group(1).strip().replace("^", "**")
            return f"print({expr})"
        wp_expr = self._extract_word_problem(message)
        if wp_expr is not None:
            return f"print({wp_expr})"
        return None

    @staticmethod
    def _extract_word_problem(message: str) -> Optional[str]:
        msg = message.lower()
        sub_patterns = [
            r"\b(?:i\s+(?:have|had|got|started\s+with|bought))\s+(\d+)\s+\w+\s+(?:and|then)\s+give\s+away\s+(\d+)",
            r"\bif\s+i\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
            r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+i\s+remove\s+(\d+)",
            r"\bstart\s+with\s+(\d+)\s+and\s+subtract\s+(\d+)",
            r"\bstart\s+with\s+(\d+)\s+and\s+take\s+away\s+(\d+)",
            r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
            r"\bi\s+have\s+(\d+)\s+and\s+give\s+away\s+(\d+)",
            r"\b(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
        ]
        for pattern in sub_patterns:
            m = re.search(pattern, msg)
            if m:
                return f"{m.group(1)} - {m.group(2)}"
        add_patterns = [
            r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+(?:get|add|receive)\s+(\d+)\s+more",
            r"\bstart\s+with\s+(\d+)\s+and\s+add\s+(\d+)",
            r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+(\d+)\s+more",
        ]
        for pattern in add_patterns:
            m = re.search(pattern, msg)
            if m:
                return f"{m.group(1)} + {m.group(2)}"
        mul_patterns = [
            r"\bwhat\s+is\s+(\d+)\s+times\s+(\d+)",
            r"\b(\d+)\s+groups?\s+of\s+(\d+)",
        ]
        for pattern in mul_patterns:
            m = re.search(pattern, msg)
            if m:
                return f"{m.group(1)} * {m.group(2)}"
        return None