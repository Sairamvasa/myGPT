"""Regression tests for plain ordinary-chat routing through both endpoints."""

import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
from agents.agent import Agent


MESSAGES = [
    "hi",
    "hello",
    "What is Python?",
]

MATH_MESSAGES = [
    "What is 2+2?",
]
FORBIDDEN = (
    "direct answer",
    "final answer",
    "the user's request",
    "user's request",
    "context safety",
    "quality check",
    "reviewer",
    "meta-analysis",
)


def assert_plain_prompt(prompt, message):
    assert prompt == message
    lowered = prompt.lower()
    assert not any(term in lowered for term in FORBIDDEN)


def test_agent_keeps_ordinary_messages_plain():
    agent = Agent()
    for message in MESSAGES:
        result = agent.run(message, chat_id=42, user_id=7)
        assert result["action"] == "chat"
        assert_plain_prompt(result["prompt"], message)

    # Math messages should route to python
    for message in MATH_MESSAGES:
        result = agent.run(message, chat_id=42, user_id=7)
        assert result["action"] == "python"


def test_chat_endpoint_passes_plain_messages_to_ollama():
    captured = []

    def fake_ask(prompt, action, **kwargs):
        captured.append(prompt)
        return "Hi! How can I help you?"

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch.object(app_module, "ask_llm_routed", side_effect=fake_ask),
        ):
            client = TestClient(app_module.app)
            for message in MESSAGES:
                response = client.post(
                    "/chat",
                    json={"message": message, "chat_id": 42},
                )
                assert response.status_code == 200
                assert response.json()["answer"] == "Hi! How can I help you?"
    finally:
        app_module.app.dependency_overrides.clear()

    assert captured == MESSAGES


def test_stream_endpoint_passes_plain_messages_to_ollama():
    captured = []

    def fake_stream(prompt, action, **kwargs):
        captured.append(prompt)
        yield "Hi! How can I help you?"

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch.object(app_module, "is_first_message", return_value=False),
            patch.object(app_module, "stream_llm_routed", side_effect=fake_stream),
        ):
            client = TestClient(app_module.app)
            for message in MESSAGES:
                response = client.post(
                    "/stream",
                    json={"message": message, "chat_id": 42},
                )
                assert response.status_code == 200
                assert response.text == "Hi! How can I help you?"
    finally:
        app_module.app.dependency_overrides.clear()

    assert captured == MESSAGES


if __name__ == "__main__":
    test_agent_keeps_ordinary_messages_plain()
    test_chat_endpoint_passes_plain_messages_to_ollama()
    test_stream_endpoint_passes_plain_messages_to_ollama()
    print("PASS: ordinary chat routing is plain for Agent, /chat, and /stream")
