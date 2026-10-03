"""Permission and risk evaluation for MyGPT tools."""

from __future__ import annotations

from dataclasses import dataclass

from agents.tool_registry import RiskLevel, Tool, ToolError, ToolRegistry


class PermissionDecision:
    """Possible outcomes of a tool permission check."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionResult:
    """Result of evaluating whether a tool may execute."""

    decision: str
    tool_name: str
    risk_level: str | None = None
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == PermissionDecision.ALLOW

    @property
    def requires_confirmation(self) -> bool:
        return self.decision == PermissionDecision.CONFIRM


def evaluate_tool_permission(
    registry: ToolRegistry,
    tool_name: str,
    *,
    user_confirmed: bool = False,
) -> PermissionResult:
    """
    Evaluate whether a registered tool may execute.

    Rules:
    - Unknown tools are denied.
    - Tools requiring confirmation need explicit confirmation.
    - Already-confirmed tools are allowed.
    - Tools that do not require confirmation are allowed.
    - Risk level is preserved in the result for auditing and policy decisions.
    """

    if not tool_name or not isinstance(tool_name, str):
        return PermissionResult(
            decision=PermissionDecision.DENY,
            tool_name=tool_name or "",
            reason="Invalid tool name.",
        )

    try:
        tool: Tool = registry.get(tool_name)
    except ToolError:
        return PermissionResult(
            decision=PermissionDecision.DENY,
            tool_name=tool_name,
            reason=f"Unknown tool: {tool_name}",
        )

    risk_level = tool.risk_level

    if risk_level not in RiskLevel.VALUES:
        return PermissionResult(
            decision=PermissionDecision.DENY,
            tool_name=tool_name,
            risk_level=risk_level,
            reason="Tool has an invalid risk level.",
        )

    if tool.requires_confirmation and not user_confirmed:
        return PermissionResult(
            decision=PermissionDecision.CONFIRM,
            tool_name=tool_name,
            risk_level=risk_level,
            reason=(
                "Tool requires explicit user confirmation "
                f"before execution (risk={risk_level})."
            ),
        )

    return PermissionResult(
        decision=PermissionDecision.ALLOW,
        tool_name=tool_name,
        risk_level=risk_level,
        reason=(
            "Tool is permitted to execute."
            f" (risk={risk_level}, confirmation={user_confirmed})"
        ),
    )