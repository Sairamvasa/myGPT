"""Latency benchmark for BEFORE vs AFTER comparison."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide
from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options, OLLAMA_NUM_PREDICT

client = _get_client()

print(f"OLLAMA_NUM_PREDICT = {OLLAMA_NUM_PREDICT}")
print(f"Client type: {type(client).__name__}")

def ollama_stream(prompt, model=OLLAMA_MODEL):
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    token_count = 0
    for resp in client.chat(model=model, messages=_chat_messages(prompt), stream=True, options=_generation_options(), keep_alive="10m"):
        if t_first is None:
            t_first = (time.perf_counter() - t0) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            total_text += content
            token_count += len(content.split())
        if resp.get("done"):
            break
    total = (time.perf_counter() - t0) * 1000
    return t_first, total, total_text, token_count

def run_case(name, message, user_id=None, chat_id=None):
    print(f"\n=== {name}: {message!r} ===", flush=True)

    t0 = time.perf_counter()
    action = decide(message)
    t_planner = (time.perf_counter() - t0) * 1000

    agent = Agent()
    t0 = time.perf_counter()
    result = agent.run(message, chat_id=chat_id, user_id=user_id)
    t_agent = (time.perf_counter() - t0) * 1000

    prompt = result["prompt"]
    ttft, t_ollama, text, tok_count = ollama_stream(prompt)
    total = t_planner + t_agent + t_ollama

    print(f"  planner={t_planner:.1f}ms agent={t_agent:.1f}ms action={result['action']}", flush=True)
    print(f"  prompt_len={len(prompt)} ollama_ttft={ttft:.1f}ms ollama_total={t_ollama:.1f}ms", flush=True)
    print(f"  tokens={tok_count} TOTAL={total:.0f}ms resp={text[:100]!r}", flush=True)

    return dict(name=name, planner=round(t_planner,1), agent=round(t_agent,1),
                ollama_ttft=round(ttft,1), ollama_total=round(t_ollama,1),
                total=round(total,0), prompt_len=len(prompt), action=result["action"],
                has_context=bool(result.get("context")), tokens=tok_count,
                response=text)

results = []
results.append(run_case("A: hi", "hi"))
results.append(run_case("B: What is Python?", "What is Python?"))
results.append(run_case("C: What is 2+2?", "What is 2+2?"))
long_q = "Explain how Python handles memory management, garbage collection, and reference counting in simple terms."
results.append(run_case("D: longer normal question", long_q))

# E & F: RAG
CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id_e = 8002
rag_dir = os.path.join("rag_indexes", str(user_id_e))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
from rag import process_text_file
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp_e = f.name
process_text_file(tmp_e, user_id_e, source_filename="calculator.py")
os.unlink(tmp_e)
results.append(run_case("E: RAG 'Explain this code'", "Explain this code", user_id=user_id_e, chat_id=1))
results.append(run_case("F: RAG 'What is the output?'", "What is the output?", user_id=user_id_e, chat_id=1))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n\n===== AFTER TIMING TABLE =====")
print(f"{'Case':<30} {'Planner':>8} {'Agent':>8} {'TTFT':>8} {'OllamaTot':>10} {'Total':>8} {'Tokens':>7} {'Action':>8} {'Ctx':>5}")
for r in results:
    print(f"{r['name']:<30} {r['planner']:>7.1f} {r['agent']:>7.1f} {r['ollama_ttft']:>7.1f} {r['ollama_total']:>9.1f} {r['total']:>7.0f} {r['tokens']:>6} {r['action']:>8} {str(r['has_context']):>5}")

print("\n===== RESPONSES =====")
for r in results:
    print(f"\n--- {r['name']} ---")
    print(r['response'][:300])

with open(os.path.join(os.path.dirname(__file__), "diag_after.json"), "w") as f:
    json.dump([{k: v for k, v in r.items() if k != 'response'} for r in results], f, indent=2)
print("\nResults saved to diag_after.json")