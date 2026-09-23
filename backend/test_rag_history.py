"""Test: RAG requests receive zero history, normal chat unchanged."""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from unittest.mock import patch
from agents.agent import Agent
from agents.planner import decide

# --- Test 1: Normal chat now includes full history ---
print("=" * 60)
print("TEST 1: Normal chat includes full history")
print("=" * 60)

with patch("agents.agent.get_history") as mock_history:
    mock_history.return_value = [
        ("user", "message 1"),
        ("user", "message 2"),
        ("user", "message 3"),
        ("user", "message 4"),
        ("user", "message 5"),
        ("user", "message 6"),
        ("user", "message 7"),
        ("user", "message 8"),
        ("user", "message 9"),
        ("user", "message 10"),
    ]
    agent = Agent()
    result = agent.run("What is Python?", chat_id=1, user_id=1)
    assert result["action"] == "chat"
    assert len(result["history"]) == 10, f"Expected 10 history messages for plain chat, got {len(result['history'])}"
    assert "message 1" in result["prompt"], "History should be included in chat prompt"
    print("  PASS: normal chat includes full history in prompt")

# --- Test 2: RAG request receives ZERO history messages ---
print("\n" + "=" * 60)
print("TEST 2: RAG request receives zero history messages")
print("=" * 60)

with patch("agents.agent.get_history") as mock_history:
    mock_history.return_value = [
        ("user", "old message 1"),
        ("user", "old message 2"),
        ("user", "old message 3"),
        ("user", "old message 4"),
        ("user", "old message 5"),
        ("user", "old message 6"),
        ("user", "old message 7"),
        ("user", "old message 8"),
        ("user", "old message 9"),
        ("user", "old message 10"),
    ]
    agent = Agent()
    result = agent.run("Explain this code", chat_id=1, user_id=1)
    assert result["action"] == "rag", f"Expected action=rag, got {result['action']}"
    assert len(result["history"]) == 0, f"Expected 0 history messages, got {len(result['history'])}"
    print(f"  PASS: RAG history is empty: {result['history']}")

# --- Test 3: RAG context is still included ---
print("\n" + "=" * 60)
print("TEST 3: RAG context is still included in prompt")
print("=" * 60)

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9501
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

from rag import process_text_file
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

with patch("agents.agent.get_history") as mock_history:
    mock_history.return_value = [
        ("user", "factorial program"),
        ("assistant", "Here is the factorial program..."),
        ("user", "in java"),
        ("assistant", "Here is the factorial in Java..."),
        ("user", "in c"),
        ("assistant", "Here is the factorial in C..."),
    ]
    agent = Agent()
    result = agent.run("What is the output?", chat_id=1, user_id=user_id)
    assert result["action"] == "rag"
    assert result["context"] is not None
    assert "calculator.py" in result["context"]
    assert "def add(a, b)" in result["context"]
    assert "print(x)" in result["context"]
    assert len(result["history"]) == 0, f"Expected 0 history, got {len(result['history'])}"
    print(f"  PASS: RAG context present, history is empty")
    print(f"  History: {result['history']}")

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# --- Test 4: Non-RAG actions keep full history ---
print("\n" + "=" * 60)
print("TEST 4: Non-RAG actions keep full history")
print("=" * 60)

with patch("agents.agent.get_history") as mock_history:
    big_history = [(f"user", f"msg {i}") for i in range(1, 11)]
    mock_history.return_value = big_history
    agent = Agent()
    result = agent.run("What time is it?", chat_id=1, user_id=1)
    assert result["action"] == "time"
    assert len(result["history"]) == 10, f"Expected 10 history messages for time action, got {len(result['history'])}"
    print(f"  PASS: time action keeps full history ({len(result['history'])} messages)")

# --- Test 5: Web search action keeps full history ---
print("\n" + "=" * 60)
print("TEST 5: Web search action keeps full history")
print("=" * 60)

with patch("agents.agent.get_history") as mock_history:
    big_history = [(f"user", f"msg {i}") for i in range(1, 11)]
    mock_history.return_value = big_history
    agent = Agent()
    result = agent.run("What is the latest news?", chat_id=1, user_id=1)
    assert result["action"] == "web"
    assert len(result["history"]) == 10, f"Expected 10 history messages for web action, got {len(result['history'])}"
    print(f"  PASS: web action keeps full history ({len(result['history'])} messages)")

# --- Test 6: RAG with no history (edge case) ---
print("\n" + "=" * 60)
print("TEST 6: RAG with no history (edge case)")
print("=" * 60)

with patch("agents.agent.get_history") as mock_history:
    mock_history.return_value = []
    agent = Agent()
    result = agent.run("Find any problems in this code", chat_id=1, user_id=1)
    assert result["action"] == "rag"
    assert len(result["history"]) == 0
    print("  PASS: RAG with no history keeps empty")

# --- Test 7: Prompt does NOT contain history for RAG ---
print("\n" + "=" * 60)
print("TEST 7: RAG prompt does NOT contain old conversation history")
print("=" * 60)

CALC2 = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id7 = 9601
rag_dir7 = os.path.join("rag_indexes", str(user_id7))
if os.path.exists(rag_dir7):
    shutil.rmtree(rag_dir7)

from rag import process_text_file
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC2)
    tmp7 = f.name
process_text_file(tmp7, user_id7, source_filename="calculator.py")
os.unlink(tmp7)

with patch("agents.agent.get_history") as mock_history:
    mock_history.return_value = [
        ("user", "factorial program"),
        ("assistant", "Here is the factorial program..."),
        ("user", "in java"),
        ("assistant", "Here is the factorial in Java..."),
        ("user", "in c"),
        ("assistant", "Here is the factorial in C..."),
    ]
    agent = Agent()
    result = agent.run("Explain this code", chat_id=1, user_id=user_id7)
    prompt = result["prompt"]
    assert "factorial program" not in prompt.lower(), "Old factorial history should NOT be in RAG prompt"
    assert "in java" not in prompt.lower(), "Old java history should NOT be in RAG prompt"
    assert "in c" not in prompt.lower(), "Old C history should NOT be in RAG prompt"
    assert "def add(a, b)" in prompt, "calculator.py content should be in prompt"
    print("  PASS: RAG prompt contains no old history, contains calculator.py content")

if os.path.exists(rag_dir7):
    shutil.rmtree(rag_dir7)

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)