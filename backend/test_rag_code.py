"""End-to-end test for uploaded-file RAG with code analysis questions."""

import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide
from agents.agent import Agent
from rag import process_text_file, search_pdf


CALCULATOR_PY = """def add(a, b):
    return a + b

x = add(10, 20)
print(x)
"""


def test_planner_routes_code_analysis_to_rag():
    """Code-analysis questions must route to RAG or code_explanation."""
    assert decide("Explain this code") in ("rag", "code_explanation")
    assert decide("What is the output?") == "rag"
    assert decide("Find any problems in this code") == "rag"
    assert decide("What does this code do?") in ("rag", "code_explanation")
    assert decide("How does this code work?") in ("rag", "code_explanation")
    assert decide("Review this code") in ("rag", "code_explanation")
    assert decide("Analyze this code") in ("rag", "code_explanation")
    assert decide("Bug in this code") == "rag"
    assert decide("Error in this code") == "rag"
    assert decide("What does this file do?") in ("rag", "code_explanation")
    assert decide("What does this script do?") in ("rag", "code_explanation")
    assert decide("What does this function do?") in ("rag", "code_explanation")
    assert decide("Problems in this code") == "rag"


def test_planner_keeps_plain_chat():
    """Unrelated questions must stay plain chat."""
    assert decide("hi") == "chat"
    assert decide("hello") == "chat"
    assert decide("What is Python?") == "chat"
    assert decide("How are you?") == "chat"
    assert decide("Tell me a joke") in ("chat", "creative")


def test_rag_upload_and_retrieve():
    """Upload calculator.py and verify RAG retrieval works."""
    user_id = 9999  # isolated test user
    rag_dir = os.path.join("rag_indexes", str(user_id))
    # Clean any prior state for this test user
    import shutil
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(CALCULATOR_PY)
        tmp_path = f.name

    try:
        chunks = process_text_file(tmp_path, user_id, source_filename="calculator.py")
        assert chunks > 0, f"Expected > 0 chunks, got {chunks}"

        # Verify retrieval returns content for each question
        for question in [
            "Explain this code",
            "What is the output?",
            "Find any problems in this code",
        ]:
            context = search_pdf(question, user_id)
            assert context is not None, f"RAG returned None for: {question}"
            assert "calculator.py" in context, f"calculator.py missing from context for: {question}"
            assert "def add" in context or "add(a, b)" in context, (
                f"add() function missing from context for: {question}"
            )
            print(f"  OK: '{question}' -> context len={len(context)}")
    finally:
        os.unlink(tmp_path)
        if os.path.exists(rag_dir):
            shutil.rmtree(rag_dir)


def test_agent_rag_with_uploaded_file():
    """Agent routes to rag/code_explanation and returns context when file is uploaded."""
    user_id = 9998
    rag_dir = os.path.join("rag_indexes", str(user_id))
    import shutil
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(CALCULATOR_PY)
        tmp_path = f.name

    try:
        process_text_file(tmp_path, user_id, source_filename="calculator.py")

        agent = Agent()
        for question in [
            "Explain this code",
            "What is the output?",
            "Find any problems in this code",
        ]:
            result = agent.run(question, chat_id=1, user_id=user_id)
            assert result["action"] in ("rag", "code_explanation"), (
                f"Expected action=rag or code_explanation for '{question}', got {result['action']}"
            )
            assert result["context"] is not None, (
                f"Expected non-None context for '{question}'"
            )
            assert result["tool_results"] is not None, (
                f"Expected tool_results for '{question}'"
            )
            assert "calculator.py" in result["context"], (
                f"calculator.py missing from context for '{question}'"
            )
            print(f"  OK: '{question}' -> action={result['action']}, context_len={len(result['context'])}")
    finally:
        os.unlink(tmp_path)
        if os.path.exists(rag_dir):
            shutil.rmtree(rag_dir)


def test_agent_falls_back_to_chat_when_no_context():
    """When RAG returns no context, agent must fall back to plain chat."""
    user_id = 9997
    rag_dir = os.path.join("rag_indexes", str(user_id))
    import shutil
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

    agent = Agent()
    # No files uploaded for this user
    result = agent.run("Explain this code", chat_id=1, user_id=user_id)
    assert result["action"] == "chat", (
        f"Expected fallback to chat, got action={result['action']}"
    )
    assert result["context"] is None
    assert result["tool_results"] is None
    # Prompt should NOT contain actual document content (just the "no documents" notice)
    assert "calculator.py" not in result["prompt"], (
        "Prompt should not reference uploaded file content when no files exist"
    )
    print("  OK: no-file fallback -> action=chat, no file content in prompt")


def test_rag_unrelated_question_stays_plain():
    """A question with no uploaded files stays plain chat."""
    user_id = 9996
    rag_dir = os.path.join("rag_indexes", str(user_id))
    import shutil
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

    agent = Agent()
    result = agent.run("Tell me a joke", chat_id=1, user_id=user_id)
    assert result["action"] in ("chat", "creative")
    print("  OK: unrelated question -> action=chat or creative")


if __name__ == "__main__":
    print("=== test_planner_routes_code_analysis_to_rag ===")
    test_planner_routes_code_analysis_to_rag()
    print("PASS\n")

    print("=== test_planner_keeps_plain_chat ===")
    test_planner_keeps_plain_chat()
    print("PASS\n")

    print("=== test_rag_upload_and_retrieve ===")
    test_rag_upload_and_retrieve()
    print("PASS\n")

    print("=== test_agent_rag_with_uploaded_file ===")
    test_agent_rag_with_uploaded_file()
    print("PASS\n")

    print("=== test_agent_falls_back_to_chat_when_no_context ===")
    test_agent_falls_back_to_chat_when_no_context()
    print("PASS\n")

    print("=== test_rag_unrelated_question_stays_plain ===")
    test_rag_unrelated_question_stays_plain()
    print("PASS\n")

    print("ALL TESTS PASSED")