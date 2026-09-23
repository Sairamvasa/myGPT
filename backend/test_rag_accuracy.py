"""Test RAG accuracy after prompt fix."""
import os, sys, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide
from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9101
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name

process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

client = _get_client()

def ask_ollama(prompt, max_tokens=256):
    t0 = time.perf_counter()
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=False,
        options={**_generation_options(), "num_predict": max_tokens},
        keep_alive="10m",
    )
    dt = (time.perf_counter() - t0) * 1000
    text = resp.get("message", {}).get("content", "").strip()
    return text, dt

agent = Agent()

# Test 1: "What is the output?"
print("=" * 60)
print("TEST: What is the output?")
print("=" * 60)
result = agent.run("What is the output?", chat_id=1, user_id=user_id)
print(f"Action: {result['action']}")
print(f"Has context: {result['context'] is not None}")
print(f"Prompt length: {len(result['prompt'])}")

text, dt = ask_ollama(result["prompt"])
print(f"Ollama time: {dt:.0f}ms")
print(f"Response: {text}")

# Check if response references the actual code
has_add = "add" in text.lower()
has_30 = "30" in text
has_factorial = "factorial" in text.lower()
print(f"\nReferences 'add': {has_add}")
print(f"References '30': {has_30}")
print(f"References 'factorial' (BAD): {has_factorial}")

# Test 2: "Explain this code"
print("\n" + "=" * 60)
print("TEST: Explain this code")
print("=" * 60)
result2 = agent.run("Explain this code", chat_id=1, user_id=user_id)
text2, dt2 = ask_ollama(result2["prompt"])
print(f"Ollama time: {dt2:.0f}ms")
print(f"Response: {text2[:300]}")

# Test 3: "Find any problems in this code"
print("\n" + "=" * 60)
print("TEST: Find any problems in this code")
print("=" * 60)
result3 = agent.run("Find any problems in this code", chat_id=1, user_id=user_id)
text3, dt3 = ask_ollama(result3["prompt"])
print(f"Ollama time: {dt3:.0f}ms")
print(f"Response: {text3[:300]}")

# Test 4: Normal chat (no RAG)
print("\n" + "=" * 60)
print("TEST: Normal chat 'hi' (should NOT trigger RAG)")
print("=" * 60)
result4 = agent.run("hi", chat_id=1, user_id=user_id)
print(f"Action: {result4['action']}")
print(f"Has context: {result4['context'] is not None}")
text4, dt4 = ask_ollama(result4["prompt"])
print(f"Ollama time: {dt4:.0f}ms")
print(f"Response: {text4}")

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)