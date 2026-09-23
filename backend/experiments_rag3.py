"""Experiment 3: Isolate whether SYSTEM_PROMPT is the root cause."""
import os
import sys
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file
from agents.prompts import SYSTEM_PROMPT

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

user_id = 9803
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

def ask(messages, num_predict=160, temperature=0.2, top_p=0.9):
    t0 = time.perf_counter()
    t_first = None
    text = ""
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
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

# Build the exact production prompt sections
from agents.prompt_builder import build_prompt
prompt = build_prompt(
    question="What is the output?",
    history=[],
    memories=[],
    context="UPLOADED DOCUMENTS:\n- calculator.py\n\n===== DOCUMENT: calculator.py =====\n\nSOURCE: calculator.py\nPAGE: 1\n\ndef add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)",
    tool_results="Document context retrieved from uploaded files \u2014 answer based on the document content above."
)

print("=" * 80)
print("TEST A: Full SYSTEM_PROMPT + production prompt")
print("=" * 80)
answer, ttft, total, ec, pec = ask([
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": prompt},
])
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct (30): {'30' in answer}")
print()

print("=" * 80)
print("TEST B: SHORT system prompt + production prompt")
print("=" * 80)
short_sys = "You are a helpful assistant. Answer questions based on the provided context."
answer, ttft, total, ec, pec = ask([
    {"role": "system", "content": short_sys},
    {"role": "user", "content": prompt},
])
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct (30): {'30' in answer}")
print()

print("=" * 80)
print("TEST C: NO system prompt + production prompt")
print("=" * 80)
answer, ttft, total, ec, pec = ask([
    {"role": "user", "content": prompt},
])
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct (30): {'30' in answer}")
print()

print("=" * 80)
print("TEST D: Full SYSTEM_PROMPT + minimal prompt (code + question)")
print("=" * 80)
minimal = f"Code:\n{CALC}\n\nWhat is the output?"
answer, ttft, total, ec, pec = ask([
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": minimal},
])
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct (30): {'30' in answer}")
print()

print("=" * 80)
print("TEST E: Full SYSTEM_PROMPT + code + 'What is the output?' (no sections)")
print("=" * 80)
plain = f"Here is a Python file called calculator.py:\n\n{CALC}\n\nWhat is the output of this code?"
answer, ttft, total, ec, pec = ask([
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": plain},
])
print(f"Answer: {answer!r}")
print(f"TTFT={ttft:.0f}ms Total={total:.0f}ms EvalTokens={ec} PromptTokens={pec}")
print(f"Correct (30): {'30' in answer}")
print()

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)