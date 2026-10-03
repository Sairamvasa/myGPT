from agents.planner import (
    ACTION_PYTHON,
    ACTION_TIME,
    ACTION_WEB,
    ACTION_RAG,
    ACTION_VISION,
    ACTION_IMAGE_GEN,
)

from agents.tool_selector import select_tool


def test_select_python_tool():
    assert select_tool(ACTION_PYTHON) == "python_exec"


def test_select_time_tool():
    assert select_tool(ACTION_TIME) == "get_current_time"


def test_select_web_tool():
    assert select_tool(ACTION_WEB) == "web_search"


def test_select_rag_tool():
    assert select_tool(ACTION_RAG) == "rag_search"


def test_select_vision_tool():
    assert select_tool(ACTION_VISION) == "vision"


def test_select_image_generation_tool():
    assert select_tool(ACTION_IMAGE_GEN) == "image_gen"


def test_non_tool_action_returns_none():
    assert select_tool("chat") is None
