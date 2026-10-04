from agents.agent import Agent
from agents.planner import (
    ACTION_WEB,
    ACTION_WEB_RESEARCH,
)
from agents import tools


def _fake_web_search(query, max_results=5):
    return {
        "original_query": query,
        "final_query": query,
        "reformulated": False,
        "reformulation_reason": None,
        "total_found": 3,
        "returned": 3,
        "results": [
            {
                "title": "Example AI News",
                "url": "https://example.com/ai",
                "snippet": "Example AI development result.",
            },
            {
                "title": "Example NVIDIA News",
                "url": "https://example.com/nvidia",
                "snippet": "Example NVIDIA technology result.",
            },
            {
                "title": "Example Technology News",
                "url": "https://example.com/technology",
                "snippet": "Example technology result.",
            },
        ],
    }


def test_web_search_orchestration(monkeypatch):
    monkeypatch.setattr(
        tools,
        "web_search",
        _fake_web_search,
    )

    agent = Agent()

    result = agent.run(
        "search the web for the latest AI developments"
    )

    assert result["action"] == ACTION_WEB
    assert result["tool_results"] is not None
    assert "Tool: web_search" in result["tool_results"]
    assert "Status: success" in result["tool_results"]
    assert "Example AI News" in result["tool_results"]


def test_current_info_uses_web_tool(monkeypatch):
    monkeypatch.setattr(
        tools,
        "web_search",
        _fake_web_search,
    )

    agent = Agent()

    result = agent.run(
        "What is the latest news about NVIDIA?"
    )

    assert result["action"] == ACTION_WEB_RESEARCH
    assert result["tool_results"] is not None
    assert "Tool: web_search" in result["tool_results"]
    assert "Status: success" in result["tool_results"]
    assert "Example NVIDIA News" in result["tool_results"]


def test_web_research_orchestration(monkeypatch):
    monkeypatch.setattr(
        tools,
        "web_search",
        _fake_web_search,
    )

    agent = Agent()

    result = agent.run(
        "research the latest developments in artificial intelligence"
    )

    assert result["action"] == ACTION_WEB_RESEARCH
    assert result["tool_results"] is not None
    assert "Tool: web_search" in result["tool_results"]
    assert "Status: success" in result["tool_results"]
    assert "Example AI News" in result["tool_results"]