"""Experiment 2: Test with duplicated context (as seen in production) and other variations."""
import os
import sys
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file
from agents.agent import Agent
from agents.prompt_builder import build_prompt

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

user_id = 9802
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name

process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

client = _get_client()

def ask(prompt, num_predict=160, temperature=0.2, top_p=0.9):
    t0 = time.perf_counter()
    t_first = None
    text = ""
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=True,
        options={**_generation_options(), "num_predict": num_predict, "temperature": temperature, "top_p": top_p},
        keep_alive="10m",
    ):
        if t_first is None:
            t_first = (time.perf_counter() - t0) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            text += content
        if resp.get("done"):
            break
    t_total = (time.perf_counter() - t0) * 1000
    eval_count = resp.get("eval_count", 0)
    prompt_eval_count = resp.get("prompt_eval_count", 0)
    return text.strip(), t_first, t_total, eval_count, prompt_eval_count

# Get the production prompt
agent = Agent()
result = agent.run("What is the output?", chat_id=chat_id, user_id=user_id)
full_prompt = result["prompt"]

print("=" * 80)
print("TEST 1: Full production prompt (baseline)")
print("=" * 80)
answer, ttft, total, ec, pec = ask(full_prompt)
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct: {'30' in answer}")
print()

# Test 2: Same prompt but with system prompt stripped
print("=" * 80)
print("TEST 2: Production prompt WITHOUT system prompt")
print("=" * 80)
t0 = time.perf_counter()
resp = client.chat(
    model=OLLAMA_MODEL,
    messages=[{"role": "user", "content": full_prompt}],
    stream=True,
    options={**_generation_options(), "num_predict": 160},
    keep_alive="10m",
)
t_first = (time.perf_counter() - t0) * 1000
text = ""
for r in resp:
    content = r.get("message", {}).get("content", "")
    if content:
        text += content
    if r.get("done"):
        break
t_total = (time.perf_counter() - t0) * 1000
answer = text.strip()
print(f"Answer: {answer!r}")
print(f"TTFT={t_first:.0f}ms Total={t_total:.0f}ms")
print(f"Correct: {'30' in answer}")
print()

# Test 3: Just the code block with no system prompt
print("=" * 80)
print("TEST 3: Bare code + question, no system prompt")
print("=" * 80)
bare = f"Code:\n{CALC}\n\nWhat is the output?"
answer, ttft, total, ec, pec = ask(bare)
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms")
print(f"Correct: {'30' in answer}")
print()

# Test 4: With system prompt but no other sections
print("=" * 80)
print("TEST 4: System prompt + code + question only")
print("=" * 80)
from agents.prompts import SYSTEM_PROMPT
simple = f"Code:\n{CALC}\n\nQuestion: What is the output?"
answer, ttft, total, ec, pec = ask(simple)
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms")
print(f"Correct: {'30' in answer}")
print()

# Test 5: With the context duplicated (as it appears in the actual prompt)
print("=" * 80)
print("TEST 5: Duplicated code context (as in actual prompt)")
print("=" * 80)
dup_prompt = f"""### Document & Knowledge Context
Use this uploaded document context to answer accurately.
UPLOADED DOCUMENTS:
- calculator.py

===== DOCUMENT: calculator.py =====

SOURCE: calculator.py
PAGE: 1

def add(a, b):
    return a + b

x = add(10, 20)
print(x)


SOURCE: calculator.py
PAGE: 1

def add(a, b):
    return a + b

x = add(10, 20)
print(x)


### Current User Request
What is the output?"""
answer, ttft, total, ec, pec = ask(dup_prompt)
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms")
print(f"Correct: {'30' in answer}")
print()

# Test 6: With the full prompt but asking "what is 1+2"
print("=" * 80)
print("TEST 6: Full prompt with ambiguous question")
print("=" * 80)
ambig = f"""### Document & Knowledge Context
Use this uploaded document context to answer accurately.
UPLOADED DOCUMENTS:
- calculator.py

===== DOCUMENT: calculator.py =====

SOURCE: calculator.py
PAGE: 1

def add(a, b):
    return a + b

x = add(10, 20)
print(x)


### Current User Request
What is 1 + 2?"""
answer, ttft, total, ec, pec = ask(ambig)
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms")
print(f"Correct: {'30' in answer}")
print()

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)