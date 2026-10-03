"""Tests for the agent pipeline: Agent.run, build_prompt, sequence detection,
memory extraction, and grounding."""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Agent.run
# ---------------------------------------------------------------------------

class TestAgentRun:
    """Test the Agent.run() method with various actions."""

    def test_agent_simple_chat(self, tmp_db, monkeypatch):
        """A simple chat message returns a prompt and ACTION_CHAT."""
        from agents.agent import Agent
        from agents.planner import ACTION_CHAT

        agent = Agent()
        result = agent.run("Hello, how are you?")
        assert result["action"] == ACTION_CHAT
        assert result["answer"] is None
        assert "Hello, how are you?" in result["prompt"]

    def test_agent_math_returns_direct_answer(self, tmp_db):
        """A math question returns a direct answer (executes Python)."""
        from agents.agent import Agent
        from agents.planner import ACTION_PYTHON

        agent = Agent()
        result = agent.run("what is 15 * 23")
        assert result["action"] == ACTION_PYTHON
        assert result["answer"] is not None
        assert "345" in result["answer"]

    def test_agent_word_problem(self, tmp_db):
        """A word problem triggers ACTION_PYTHON and executes code."""
        from agents.agent import Agent

        agent = Agent()
        result = agent.run("If I have 5 apples and give away 2, how many remain?")
        assert result["action"] == "python"
        assert result["answer"] is not None
        assert "3" in result["answer"]

    def test_agent_time_query(self, tmp_db):
        """A time question triggers ACTION_TIME and returns current time."""
        from agents.agent import Agent

        agent = Agent()
        result = agent.run("what time is it")
        assert result["action"] == "time"
        assert result["answer"] is not None
        assert "System Real-Time Clock" not in str(result.get("answer", ""))

    def test_agent_web_search(self, tmp_db, monkeypatch):
        """A web search query triggers ACTION_WEB and calls web_search."""
        from agents.agent import Agent
        from agents.planner import ACTION_WEB

        mock_result = {
            "results": [
                {"title": "Test", "body": "Test body", "link": "https://test.com"}
            ],
            "original_query": "capital of France",
            "final_query": "capital of France",
            "reformulated": False,
            "reformulation_reason": None,
            "total_found": 1,
            "returned": 1,
        }

        with patch("agents.tools.web_search", return_value=mock_result):
            agent = Agent()
            result = agent.run("what is the capital of France")

        assert result["action"] == ACTION_WEB
        assert result["tool_results"] is not None
        assert "Test" in result["tool_results"]

    def test_agent_code_generation(self, tmp_db):
        """A code generation request triggers ACTION_CODE."""
        from agents.agent import Agent
        from agents.planner import ACTION_CODE

        agent = Agent()
        result = agent.run("write a python function to add two numbers")
        assert result["action"] == ACTION_CODE
        assert result["tool_results"] is not None
        assert "CODE GENERATION" in result["tool_results"]

    def test_agent_with_history(self, tmp_db):
        """Agent.run retrieves conversation history from the database."""
        from agents.agent import Agent
        from database import create_conversation, save_message

        chat_id = create_conversation(1, "Test")
        save_message(chat_id, "user", "Hello")
        save_message(chat_id, "assistant", "Hi there!")

        agent = Agent()
        result = agent.run("What did I just say?", chat_id=chat_id, user_id=1)

        assert result["history"] is not None
        assert len(result["history"]) >= 2
        assert result["history"][0][0] == "user"

    def test_agent_simple_greeting_returns_direct_answer(self, tmp_db):
        """Simple greetings return a direct answer without needing LLM."""
        from agents.agent import Agent
        from agents.planner import ACTION_CHAT

        agent = Agent()
        result = agent.run("hello")
        assert result["action"] == ACTION_CHAT
        # Simple greetings should have empty prompt (not the full message)
        assert result["answer"] is None
        assert result["prompt"] == "hello"


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Test the prompt builder."""

    def test_build_prompt_basic(self):
        from agents.prompt_builder import build_prompt

        prompt = build_prompt(
            question="Hello",
            history=[],
            memories=[],
            context=None,
            tool_results=None,
        )
        assert "Hello" in prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_prompt_with_history(self):
        from agents.prompt_builder import build_prompt

        history = [("user", "Hi"), ("assistant", "Hello! How can I help?")]
        prompt = build_prompt(
            question="What is AI?",
            history=history,
            memories=[],
            context=None,
            tool_results=None,
        )
        assert "What is AI?" in prompt
        assert "Hi" in prompt
        assert "Hello! How can I help?" in prompt

    def test_build_prompt_with_memories(self):
        from agents.prompt_builder import build_prompt

        memories = ["User's name is Alex", "User is from Canada"]
        prompt = build_prompt(
            question="What is my name?",
            history=[],
            memories=memories,
            context=None,
            tool_results=None,
        )
        assert "Alex" in prompt
        assert "Canada" in prompt

    def test_build_prompt_with_context(self):
        from agents.prompt_builder import build_prompt

        prompt = build_prompt(
            question="What does the code do?",
            history=[],
            memories=[],
            context="def foo(): pass",
            tool_results=None,
        )
        assert "def foo(): pass" in prompt
        assert "What does the code do?" in prompt

    def test_build_prompt_with_tool_results(self):
        from agents.prompt_builder import build_prompt

        prompt = build_prompt(
            question="What is the capital of France?",
            history=[],
            memories=[],
            context=None,
            tool_results="Web Search Results: Paris is the capital.",
        )
        assert "Paris" in prompt


# ---------------------------------------------------------------------------
# Sequence detection
# ---------------------------------------------------------------------------

class TestSequenceDetection:
    """Test the deterministic sequence detector."""

    def test_arithmetic_sequence(self):
        from agents.sequence_detector import detect_sequence_pattern

        result = detect_sequence_pattern([1, 3, 5, 7])
        assert result is not None
        assert result[0] == "arithmetic"
        assert result[1] == 9

    def test_geometric_sequence(self):
        from agents.sequence_detector import detect_sequence_pattern

        result = detect_sequence_pattern([2, 4, 8, 16])
        assert result is not None
        assert result[0] == "geometric"
        assert result[1] == 32

    def test_squares_sequence(self):
        from agents.sequence_detector import detect_sequence_pattern

        result = detect_sequence_pattern([1, 4, 9, 16])
        assert result is not None
        assert result[0] == "squares"
        assert result[1] == 25

    def test_fibonacci_sequence(self):
        from agents.sequence_detector import detect_sequence_pattern

        result = detect_sequence_pattern([1, 1, 2, 3, 5])
        assert result is not None
        assert result[0] == "fibonacci_like"
        assert result[1] == 8

    def test_triangular_sequence(self):
        from agents.sequence_detector import detect_sequence_pattern

        result = detect_sequence_pattern([1, 3, 6, 10])
        assert result is not None
        assert result[0] == "triangular"
        assert result[1] == 15

    def test_extract_sequence_from_message(self):
        from agents.sequence_detector import extract_sequence_from_message

        result = extract_sequence_from_message("2, 4, 8, 16, ?")
        assert result == [2, 4, 8, 16]

    def test_get_sequence_answer(self):
        from agents.sequence_detector import get_sequence_answer

        answer = get_sequence_answer("2, 4, 8, 16, ?")
        assert answer == "32"

    def test_short_sequence_returns_none(self):
        from agents.sequence_detector import detect_sequence_pattern

        assert detect_sequence_pattern([1, 2]) is None
