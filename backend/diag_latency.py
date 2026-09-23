"""Latency diagnosis for MyGPT Phase 4."""
import os, sys, time, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

import ollama
from agents.planner import decide
from agents.agent import Agent
from llm import OLLAMA_MODEL, OLLAMA_BASE_URL, _get_client, _chat_messages, _generation_options
from database import get_history, get_all_memories

client = _get_client()

def timed(label, fn):
    t0 = time.perf_counter()
    result = fn()
    dt = (time.perf_counter() - t0) * 1000
    print(f"  {label}: {dt:.1f} ms")
    return result, dt

def ollama_ttft_and_total(prompt, model=OLLAMA_MODEL):
    t0 = time.perf_counter()
    ttft = None
    total_text = ""
    t_first = None
    for resp in client.chat(model=model, messages=_chat_messages(prompt), stream=True, options=_generation_options(), keep_alive="10m"):
        if t_first is None:
            t_first = (time.perf_counter() - t0) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            total_text += content
        if resp.get("done"):
            break
    total = (time.perf_counter() - t0) * 1000
    return t_first, total, total_text

def run_case(name, message, user_id=None, chat_id=None, has_rag=False):
    print(f"\n=== CASE: {name} ===")
    print(f"  Message: {message!r}")

    # 1. Planner
    action, t_planner = timed("planner", lambda: decide(message))

    # 2. Agent (excluding Ollama)
    agent = Agent()
    t0 = time.perf_counter()
    result = agent.run(message, chat_id=chat_id, user_id=user_id)
    t_agent = (time.perf_counter() - t0) * 1000
    print(f"  agent (no LLM): {t_agent:.1f} ms  action={result['action']}")

    # 3. RAG
    t_rag = 0
    if result.get("context"):
        print(f"  RAG context len: {len(result['context'])}")
    if result["action"] == "rag" and result.get("context"):
        t_rag = t_agent  # included above
    if result["action"] == "rag" and not result.get("context"):
        print("  RAG: no context found (fallback to chat)")

    # 4. Ollama
    prompt = result["prompt"]
    print(f"  Prompt length: {len(prompt)} chars")
    ttft, t_ollama_total, text = ollama_ttft_and_total(prompt)
    print(f"  Ollama TTFT: {ttft:.1f} ms")
    print(f"  Ollama total: {t_ollama_total:.1f} ms")
    print(f"  Response: {text[:120]!r}...")

    total = t_planner + t_agent + t_ollama_total
    print(f"  TOTAL (backend): {total:.1f} ms")
    return {
        "name": name, "planner": t_planner, "agent": t_agent,
        "rag": t_rag, "ollama_ttft": ttft, "ollama_total": t_ollama_total,
        "total": total, "prompt_len": len(prompt), "action": result["action"],
        "has_context": bool(result.get("context")),
    }

results = []

# A. "hi"
results.append(run_case("A: hi", "hi"))

# B. "What is Python?"
results.append(run_case("B: What is Python?", "What is Python?"))

# C. "What is 2+2?"
results.append(run_case("C: What is 2+2?", "What is 2+2?"))

# D. Longer normal question
long_q = "Explain how Python handles memory management, garbage collection, and reference counting in simple terms."
results.append(run_case("D: longer normal question", long_q))

# E. Upload calculator.py + "Explain this code"
CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id_e = 8001
rag_dir = os.path.join("rag_indexes", str(user_id_e))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
from rag import process_text_file
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp_e = f.name
process_text_file(tmp_e, user_id_e, source_filename="calculator.py")
os.unlink(tmp_e)
results.append(run_case("E: RAG 'Explain this code'", "Explain this code", user_id=user_id_e, chat_id=1, has_rag=True))

# F. Upload calculator.py + "What is the output?"
results.append(run_case("F: RAG 'What is the output?'", "What is the output?", user_id=user_id_e, chat_id=1, has_rag=True))

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n\n===== TIMING TABLE =====")
print(f"{'Case':<35} {'Planner':>8} {'Agent':>8} {'RAG':>8} {'Ollama TTFT':>12} {'Ollama Total':>12} {'Total':>8} {'Action':>8} {'Ctx':>5}")
for r in results:
    print(f"{r['name']:<35} {r['planner']:>7.1f} {r['agent']:>7.1f} {r['rag']:>7.1f} {r['ollama_ttft']:>11.1f} {r['ollama_total']:>11.1f} {r['total']:>7.0f} {r['action']:>8} {str(r['has_context']):>5}")

print("\n===== ANALYSIS =====")
for r in sorted(results, key=lambda x: x['ollama_total'], reverse=True):
    pct = r['ollama_total'] / r['total'] * 100 if r['total'] else 0
    print(f"  {r['name']}: Ollama={r['ollama_total']:.0f}ms ({pct:.0f}% of total), planner={r['planner']:.1f}ms, agent={r['agent']:.1f}ms, prompt={r['prompt_len']}chars")