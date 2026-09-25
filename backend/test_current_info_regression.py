"""Regression tests for freshness routing and memory isolation."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from agents.memory_search import search_memories
from agents.planner import ACTION_CURRENT_INFO, ACTION_MEMORY, decide
from app import _enforce_current_info_grounding


def _search_result():
    return {
        "results": [
            {
                "title": "AP petrol prices",
                "body": "Petrol: Rs 108.50 per litre in Vijayawada.",
                "link": "https://example.test/ap-petrol",
            }
        ],
        "original_query": "today petrol prices in AP",
        "final_query": "today petrol prices in AP",
        "reformulated": False,
        "reformulation_reason": None,
        "total_found": 1,
        "returned": 1,
    }


def test_current_info_does_not_include_unrelated_memory():
    message = "today petrol prices in AP"
    assert decide(message) == ACTION_CURRENT_INFO

    with (
        patch("agents.agent.get_history", return_value=[]),
        patch(
            "agents.memory_search.get_all_memories",
            return_value=["User's name is Sairam"],
        ),
        patch("agents.agent.web_search", return_value=_search_result()),
    ):
        result = Agent().run(message, chat_id=42, user_id=7)

    assert result["action"] == ACTION_CURRENT_INFO
    assert result["memories"] == []
    assert "LONG-TERM USER MEMORY" not in result["prompt"]
    assert "User's name is Sairam" not in result["prompt"]
    assert "Rs 108.50" in result["prompt"]


def test_relevant_memory_is_still_retrieved_for_memory_question():
    with patch(
        "agents.memory_search.get_all_memories",
        return_value=["User's name is Sairam", "User likes Python"],
    ):
        assert search_memories("What is my name?", 7, action=ACTION_MEMORY) == [
            "User's name is Sairam"
        ]


def test_current_info_tool_result_reaches_final_prompt():
    with (
        patch("agents.agent.get_history", return_value=[]),
        patch("agents.agent.search_memories", return_value=[]),
        patch("agents.agent.web_search", return_value=_search_result()),
    ):
        result = Agent().run("today petrol prices in AP", chat_id=42, user_id=7)

    assert result["tool_results"]
    assert "CURRENT INFORMATION SEARCH RESULTS" in result["tool_results"]
    assert "AP petrol prices" in result["prompt"]
    assert "Rs 108.50" in result["prompt"]


def test_missing_live_data_is_safe():
    safe_results = "Web search returned no results for this current information query. Do not fabricate current prices."
    assert "couldn't verify" in _enforce_current_info_grounding(
        "Today's petrol price is Rs 99 per litre.",
        safe_results,
    ).lower()


def test_unsupported_stale_date_is_rejected():
    tool_results = (
        "CURRENT INFORMATION SEARCH RESULTS (retrieved at September 24, 2026):\n"
        "Petrol: Rs 108.50 per litre. Source: https://example.test"
    )
    answer = "As of August 11, 2026, petrol is Rs 108.50 per litre."
    assert "couldn't verify the date" in _enforce_current_info_grounding(
        answer,
        tool_results,
    ).lower()


def test_current_info_answer_is_not_truncated():
    tool_results = (
        "CURRENT INFORMATION SEARCH RESULTS:\n"
        "Petrol: Rs 108.50 per litre. Source: https://example.test"
    )
    assert _enforce_current_info_grounding(
        "Petrol in AP is Rs 108.50 per litre.",
        tool_results,
    ).endswith(".")
