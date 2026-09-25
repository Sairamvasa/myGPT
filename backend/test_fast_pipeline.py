"""Regression tests for adaptive routing and non-empty response guarantees."""

import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
from agents.agent import Agent
from agents.planner import ACTION_WEB_RESEARCH, decide


def _news_result():
    return {
        "results": [
            {
                "title": "AI news item",
                "body": "A recent AI development from a retrieved source.",
                "link": "https://example.test/ai-news",
            }
        ],
        "original_query": "latest AI news",
        "final_query": "latest AI news",
        "reformulated": False,
        "reformulation_reason": None,
        "total_found": 1,
        "returned": 1,
    }


def test_latest_news_uses_web_research_without_memory_or_rag():
    assert decide("latest AI news") == ACTION_WEB_RESEARCH
    with (
        patch("agents.agent.get_history", return_value=[]),
        patch("agents.agent.search_memories", return_value=[]),
        patch("agents.agent.web_search", return_value=_news_result()),
    ):
        result = Agent().run("latest AI news", chat_id=1, user_id=7)

    assert result["action"] == ACTION_WEB_RESEARCH
    assert result["memories"] == []
    assert result["context"] is None
    assert "AI news development" in result["prompt"] or "AI development" in result["prompt"]
    assert "CURRENT WEB RESEARCH RESULTS" in result["tool_results"]


def test_chat_never_persists_an_empty_assistant_answer():
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    saved = []
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message", side_effect=lambda *args: saved.append(args)),
            patch.object(app_module.agent, "run", return_value={
                "prompt": "latest AI news",
                "history": [],
                "context": None,
                "memories": [],
                "action": ACTION_WEB_RESEARCH,
                "tool_results": "CURRENT WEB RESEARCH RESULTS",
                "answer": None,
            }),
            patch.object(app_module, "ask_llm_routed", return_value=""),
        ):
            response = TestClient(app_module.app).post(
                "/chat",
                json={"message": "latest AI news", "chat_id": 1},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"].strip()
    assert saved[-1][1:] == ("assistant", response.json()["answer"])


def test_empty_stream_has_visible_fallback_and_is_persisted():
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    saved = []
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message", side_effect=lambda *args: saved.append(args)),
            patch.object(app_module, "is_first_message", return_value=False),
            patch.object(app_module.agent, "run", return_value={
                "prompt": "latest AI news",
                "history": [],
                "context": None,
                "memories": [],
                "action": ACTION_WEB_RESEARCH,
                "tool_results": "CURRENT WEB RESEARCH RESULTS",
                "answer": None,
            }),
            patch.object(app_module, "stream_llm_routed", return_value=iter(())),
        ):
            response = TestClient(app_module.app).post(
                "/stream",
                json={"message": "latest AI news", "chat_id": 1},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "couldn't generate an answer" in response.text.lower()
    assert saved[-1][1] == "assistant"
    assert saved[-1][2].strip()


def test_partial_web_research_stream_is_preserved_on_failure():
    def failing_stream(*_args, **_kwargs):
        yield "Partial retrieved answer"
        raise RuntimeError("provider disconnected")

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 7
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
            patch.object(app_module, "is_first_message", return_value=False),
            patch.object(app_module.agent, "run", return_value={
                "prompt": "latest AI news",
                "history": [],
                "context": None,
                "memories": [],
                "action": ACTION_WEB_RESEARCH,
                "tool_results": "CURRENT WEB RESEARCH RESULTS",
                "answer": None,
            }),
            patch.object(app_module, "stream_llm_routed", side_effect=failing_stream),
        ):
            response = TestClient(app_module.app).post(
                "/stream",
                json={"message": "latest AI news", "chat_id": 1},
            )
    finally:
        app_module.app.dependency_overrides.clear()

    assert "Partial retrieved answer" in response.text
    assert "temporarily unavailable" in response.text
