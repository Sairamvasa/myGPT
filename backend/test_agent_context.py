"""Focused regression test for authenticated agent context assembly."""

import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
from agents.agent import Agent
from agents.planner import decide


def test_normal_chat_includes_history_and_memory():
    """Normal chat must include conversation history and memories in the prompt."""
    with (
        patch("agents.agent.get_history", return_value=[("user", "Earlier question")]),
        patch("agents.agent.search_memories", return_value=["User likes concise answers"]),
    ):
        result = Agent().run("Please continue", chat_id=42, user_id=7)

    assert result["action"] == "chat"
    # The prompt must now include history and memory context
    assert "Context Safety" in result["prompt"]
    assert "Earlier question" in result["prompt"]
    assert "User likes concise answers" in result["prompt"]
    assert result["history"] == [("user", "Earlier question")]
    assert result["memories"] == ["User likes concise answers"]


def test_planner_avoids_unnecessary_web_search():
    assert decide("Help me organize my current project") == "chat"

    calls = []

    def fake_web_search(query, max_results=5):
        calls.append((query, max_results))
        return {
            "results": [
                {
                    "title": "Mock AI news",
                    "body": "A retrieved current AI news item.",
                    "link": "https://example.test/ai-news",
                }
            ],
            "original_query": query,
            "final_query": query,
            "reformulated": False,
            "reformulation_reason": None,
            "total_found": 1,
            "returned": 1,
        }

    with patch("agents.agent.web_search", side_effect=fake_web_search):
        result = Agent().run("What is the latest AI news?")

    assert result["action"] in ("web", "web_research")
    assert calls == [("What is the latest AI news?", 5)]
    assert "A retrieved current AI news item." in result["tool_results"]
    assert "Source: https://example.test/ai-news" in result["tool_results"]


def test_deterministic_time_answer_skips_llm():
    with patch("agents.agent.get_current_time", return_value="Thursday, January 01, 2026 12:00:00 PM"):
        result = Agent().run("What time is it?")

    assert result["action"] == "time"
    assert result["answer"] == "Thursday, January 01, 2026 12:00:00 PM"


def test_current_info_chat_preserves_retrieved_price_value():
    retrieved_price = "\u20b995.50/litre"
    mutated_price = "\u20b91.50/litre"

    def fake_web_search(query, max_results=5):
        return {
            "results": [
                {
                    "title": "Mock Hyderabad fuel price",
                    "body": f"PETROL_PRICE = {retrieved_price}",
                    "link": "https://example.test/fuel",
                }
            ],
            "original_query": query,
            "final_query": query,
            "reformulated": False,
            "reformulation_reason": None,
            "total_found": 1,
            "returned": 1,
        }

    def fake_ask(prompt, action, **kwargs):
        assert action == "current_info"
        assert retrieved_price in prompt
        return f"Today's petrol price is {mutated_price}."

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch("agents.agent.web_search", side_effect=fake_web_search),
            patch.object(app_module, "ask_llm_routed", side_effect=fake_ask),
        ):
            response = TestClient(app_module.app).post(
                "/chat",
                json={"message": "Today's petrol price in Hyderabad", "chat_id": 42},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    answer = response.json()["answer"]
    assert retrieved_price in answer
    assert mutated_price not in answer


def test_current_info_stream_preserves_retrieved_price_value():
    retrieved_price = "\u20b995.50/litre"
    mutated_price = "\u20b91.50/litre"

    def fake_web_search(query, max_results=5):
        return {
            "results": [
                {
                    "title": "Mock Hyderabad fuel price",
                    "body": f"PETROL_PRICE = {retrieved_price}",
                    "link": "https://example.test/fuel",
                }
            ],
            "original_query": query,
            "final_query": query,
            "reformulated": False,
            "reformulation_reason": None,
            "total_found": 1,
            "returned": 1,
        }

    def fake_stream(prompt, action, **kwargs):
        assert action == "current_info"
        assert retrieved_price in prompt
        yield f"Today's petrol price is {mutated_price}."

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch.object(app_module, "is_first_message", return_value=False),
            patch("agents.agent.web_search", side_effect=fake_web_search),
            patch.object(app_module, "stream_llm_routed", side_effect=fake_stream),
        ):
            response = TestClient(app_module.app).post(
                "/stream",
                json={"message": "Today's petrol price in Hyderabad", "chat_id": 42},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert retrieved_price in response.text
    assert mutated_price not in response.text


if __name__ == "__main__":
    test_normal_chat_includes_history_and_memory()
    test_planner_avoids_unnecessary_web_search()
    test_deterministic_time_answer_skips_llm()
    test_current_info_chat_preserves_retrieved_price_value()
    test_current_info_stream_preserves_retrieved_price_value()
    print("PASS: agent context, routing, and deterministic answers")
