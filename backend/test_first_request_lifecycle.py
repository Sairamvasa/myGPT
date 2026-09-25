"""Regression coverage for first-turn ordering and context visibility."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient

import app as app_module
from agents.agent import Agent


def test_agent_excludes_only_persisted_current_turn_from_prior_history():
    message = "What is Python?"
    with patch(
        "agents.agent.get_history",
        return_value=[("user", "Earlier question"), ("user", message)],
    ):
        result = Agent().run(message, chat_id=42, user_id=None)

    assert result["history"] == [("user", "Earlier question")]
    assert message in result["prompt"]
    assert result["prompt"].count(message) == 1


def test_first_chat_persists_user_before_agent_and_assistant_afterward():
    events = []
    message = "What is Python?"

    def fake_save(chat_id, role, content):
        events.append(("save", role, content))

    def fake_run(current_message, chat_id, user_id):
        events.append(("agent", current_message))
        return {
            "prompt": current_message,
            "history": [],
            "context": None,
            "memories": [],
            "action": "chat",
            "tool_results": None,
            "answer": None,
        }

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message", side_effect=fake_save),
            patch.object(app_module.agent, "run", side_effect=fake_run),
            patch.object(app_module, "ask_llm_routed", return_value="correct first answer"),
        ):
            response = TestClient(app_module.app).post(
                "/chat",
                json={"message": message, "chat_id": 42},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "correct first answer"
    assert events == [
        ("save", "user", message),
        ("agent", message),
        ("save", "assistant", "correct first answer"),
    ]


def test_stream_first_chat_persists_user_before_provider():
    events = []
    message = "Explain machine learning in simple words."

    def fake_save(chat_id, role, content):
        events.append(("save", role, content))

    def fake_run(current_message, chat_id, user_id):
        events.append(("agent", current_message))
        return {
            "prompt": current_message,
            "history": [],
            "context": None,
            "memories": [],
            "action": "chat",
            "tool_results": None,
            "answer": None,
        }

    def fake_stream(prompt, action, **kwargs):
        events.append(("provider", prompt))
        yield "correct first answer"

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message", side_effect=fake_save),
            patch.object(app_module.agent, "run", side_effect=fake_run),
            patch.object(app_module, "stream_llm_routed", side_effect=fake_stream),
            patch.object(app_module, "is_first_message", return_value=False),
        ):
            response = TestClient(app_module.app).post(
                "/stream",
                json={"message": message, "chat_id": 42},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "correct first answer"
    assert [event[0] for event in events] == [
        "save",
        "agent",
        "provider",
        "save",
    ]
    assert events[0][1:] == ("user", message)


def test_stream_zero_provider_chunks_returns_visible_fallback():
    message = "hello"

    def fake_run(current_message, chat_id, user_id):
        return {
            "prompt": current_message,
            "history": [],
            "context": None,
            "memories": [],
            "action": "chat",
            "tool_results": None,
            "answer": None,
        }

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch.object(app_module.agent, "run", side_effect=fake_run),
            patch.object(app_module, "stream_llm_routed", return_value=iter(())),
            patch.object(app_module, "is_first_message", return_value=False),
        ):
            response = TestClient(app_module.app).post(
                "/stream",
                json={"message": message, "chat_id": 42},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "couldn't generate an answer" in response.text
