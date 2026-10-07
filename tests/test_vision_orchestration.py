from pathlib import Path

from agents.tool_implementations import get_tool_registry
from agents.tool_validator import validate_tool_request
from agents.tool_permissions import evaluate_tool_permission
from agents.result_collector import ResultCollector
from agents.result_verifier import verify_tool_result


def test_vision_full_orchestration(monkeypatch, tmp_path):
    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake-image")

    def fake_analyze_image(path, prompt):
        assert path == str(image_path)
        assert prompt == "What is in this image?"
        return "This is a test image."

    monkeypatch.setattr(
        "vision.analyze_image",
        fake_analyze_image,
    )

    registry = get_tool_registry()

    tool_args = {
        "image_path": str(image_path),
        "prompt": "What is in this image?",
    }

    # 1. Validation
    valid, error = validate_tool_request(
        registry,
        "vision",
        tool_args,
    )

    assert valid is True
    assert error is None

    # 2. Permission
    permission = evaluate_tool_permission(
        registry,
        "vision",
        user_confirmed=False,
    )

    assert permission.allowed is True

    # 3. Execution
    result = registry.execute(
        "vision",
        tool_args,
        context=None,
    )

    assert result.success is True
    assert result.tool_name == "vision"
    assert "This is a test image." in result.output

    # 4. Collection
    collector = ResultCollector()
    collected = collector.collect(result)

    assert collected.success is True
    assert collected.status == "success"
    assert "This is a test image." in collected.text

    # 5. Verification
    verification = verify_tool_result(collected)

    assert verification.valid is True
    assert verification.verified is True


def test_vision_validation_requires_image_path():
    registry = get_tool_registry()

    valid, error = validate_tool_request(
        registry,
        "vision",
        {
            "prompt": "Describe this image.",
        },
    )

    assert valid is False
    assert "image_path" in error


def test_vision_permission_is_allowed():
    registry = get_tool_registry()

    permission = evaluate_tool_permission(
        registry,
        "vision",
        user_confirmed=False,
    )

    assert permission.allowed is True
    assert permission.requires_confirmation is False