from agents.tool_permissions import (
    PermissionDecision,
    evaluate_tool_permission,
)

from agents.tool_registry import (
    RiskLevel,
    Tool,
    ToolRegistry,
)


def make_registry():
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="safe_tool",
            description="Safe read-only tool",
            category="test",
            input_schema={},
            requires_confirmation=False,
            risk_level=RiskLevel.LOW,
            executor=lambda args, context: None,
        )
    )

    registry.register(
        Tool(
            name="medium_tool",
            description="Medium-risk tool",
            category="test",
            input_schema={},
            requires_confirmation=False,
            risk_level=RiskLevel.MEDIUM,
            executor=lambda args, context: None,
        )
    )

    registry.register(
        Tool(
            name="dangerous_tool",
            description="High-risk tool",
            category="test",
            input_schema={},
            requires_confirmation=True,
            risk_level=RiskLevel.HIGH,
            executor=lambda args, context: None,
        )
    )

    return registry


def test_low_risk_tool_is_allowed():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "safe_tool",
    )

    assert result.decision == PermissionDecision.ALLOW
    assert result.allowed is True
    assert result.risk_level == RiskLevel.LOW


def test_medium_risk_tool_without_confirmation_is_allowed_when_policy_allows_it():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "medium_tool",
    )

    assert result.decision == PermissionDecision.ALLOW
    assert result.allowed is True
    assert result.risk_level == RiskLevel.MEDIUM


def test_confirmation_required_tool_requests_confirmation():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "dangerous_tool",
    )

    assert result.decision == PermissionDecision.CONFIRM
    assert result.allowed is False
    assert result.requires_confirmation is True
    assert result.risk_level == RiskLevel.HIGH


def test_confirmed_high_risk_tool_is_allowed():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "dangerous_tool",
        user_confirmed=True,
    )

    assert result.decision == PermissionDecision.ALLOW
    assert result.allowed is True
    assert result.risk_level == RiskLevel.HIGH


def test_unknown_tool_is_denied():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "unknown_tool",
    )

    assert result.decision == PermissionDecision.DENY
    assert result.allowed is False
    assert "Unknown tool" in result.reason


def test_invalid_tool_name_is_denied():
    registry = make_registry()

    result = evaluate_tool_permission(
        registry,
        "",
    )

    assert result.decision == PermissionDecision.DENY
    assert result.allowed is False


def test_invalid_risk_level_is_denied():
    registry = ToolRegistry()

    tool = Tool(
        name="invalid_test",
        description="Invalid risk tool",
        category="test",
        input_schema={},
        risk_level=RiskLevel.LOW,
        executor=lambda args, context: None,
    )

    # Mutate after construction to test the permission layer itself.
    tool.risk_level = "invalid-risk"

    registry.register(tool)

    result = evaluate_tool_permission(
        registry,
        "invalid_test",
    )

    assert result.decision == PermissionDecision.DENY
    assert result.allowed is False
    assert "invalid risk level" in result.reason.lower()