"""Map planner actions to canonical MyGPT tools."""

from typing import Optional

from agents.planner import (
    ACTION_PYTHON,
    ACTION_TIME,
    ACTION_WEB,
    ACTION_RAG,
    ACTION_VISION,
    ACTION_IMAGE_GEN,
    ACTION_CURRENT_INFO,
    ACTION_WEB_RESEARCH,
)

ACTION_TO_TOOL = {
    ACTION_PYTHON: "python_exec",
    ACTION_TIME: "get_current_time",
    ACTION_WEB: "web_search",
    ACTION_CURRENT_INFO: "web_search",
    ACTION_WEB_RESEARCH: "web_search",
    ACTION_RAG: "rag_search",
    ACTION_VISION: "vision",
    ACTION_IMAGE_GEN: "image_gen",
}


def select_tool(action: str) -> Optional[str]:
    """Return the canonical tool name for a planner action."""
    return ACTION_TO_TOOL.get(action)
