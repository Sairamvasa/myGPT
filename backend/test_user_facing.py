"""User-facing test: upload calculator.py and ask questions, capture exact Ollama responses."""
import os, sys, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9401
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# Upload calculator.py
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)
print("calculator.py uploaded: YES")

# Simulate the same chat_id that had factorial history
# First, populate the chat history with factorial conversations
from database import save_message, get_history
# Clear any existing messages for this chat
# (We use a fresh chat_id to simulate the real scenario)
for i in range(6):
    if i % 2 == 0:
        save_message(chat_id, "user", f"factorial program {i}")
    else:
        save_message(chat_id, "assistant", f"Here is the factorial program...")

# Verify history exists
history = get_history(chat_id)
print(f"Chat history messages before questions: {len(history)}")

client = _get_client()

def ask(prompt):
    t0 = time.perf_counter()
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=False,
        options=_generation_options(),
        keep_alive="10m",
    )
    dt = (time.perf_counter() - t0) * 1000
    return resp.get("message", {}).get("content", "").strip(), dt

agent = Agent()

# Test 1: "What is the output?"
print("\n" + "=" * 60)
print("QUESTION: What is the output?")
print("=" * 60)
result = agent.run("What is the output?", chat_id=chat_id, user_id=user_id)
print(f"Action: {result['action']}")
print(f"History length in prompt: {len(result['history'])}")
text, dt = ask(result["prompt"])
print(f"Ollama time: {dt:.0f}ms")
print(f"RESPONSE:\n{text}")
print(f"\nContains '30': {'30' in text}")
print(f"Contains 'factorial': {'factorial' in text.lower()}")
print(f"Contains 'add': {'add' in text.lower()}")

# Test 2: "Explain this code"
print("\n" + "=" * 60)
print("QUESTION: Explain this code")
print("=" * 60)
result2 = agent.run("Explain this code", chat_id=chat_id, user_id=user_id)
print(f"Action: {result2['action']}")
print(f"History length in prompt: {len(result2['history'])}")
text2, dt2 = ask(result2["prompt"])
print(f"Ollama time: {dt2:.0f}ms")
print(f"RESPONSE:\n{text2}")

# Test 3: "What does this code do?"
print("\n" + "=" * 60)
print("QUESTION: What does this code do?")
print("=" * 60)
result3 = agent.run("What does this code do?", chat_id=chat_id, user_id=user_id)
print(f"Action: {result3['action']}")
print(f"History length in prompt: {len(result3['history'])}")
text3, dt3 = ask(result3["prompt"])
print(f"Ollama time: {dt3:.0f}ms")
print(f"RESPONSE:\n{text3}")

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)