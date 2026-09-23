"""Benchmark the only installed model: llama3.2:1b (baseline)."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def run(model, prompt, num_predict=160):
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    timing = {}
    for resp in client.chat(
        model=model,
        messages=_chat_messages(prompt),
        stream=True,
        options={**_generation_options(), "num_predict": num_predict},
        keep_alive="10m",
    ):
        if t_first is None:
            t_first = (time.perf_counter() - t0) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            total_text += content
        if resp.get("done"):
            timing["total_duration"] = resp.get("total_duration", 0) / 1e9
            timing["load_duration"] = resp.get("load_duration", 0) / 1e9
            timing["prompt_eval_count"] = resp.get("prompt_eval_count", 0)
            timing["eval_count"] = resp.get("eval_count", 0)
            timing["prompt_eval_duration"] = resp.get("prompt_eval_duration", 0) / 1e9
            timing["eval_duration"] = resp.get("eval_duration", 0) / 1e9
    total = (time.perf_counter() - t0) * 1000
    tokens = len(total_text.split())
    tok_per_sec = tokens / (timing["eval_duration"]) if timing.get("eval_duration") else 0
    return total_text, t_first, total, tokens, tok_per_sec, timing

def evaluate(response, question):
    r = response.lower()
    correct = True
    hallucination = []
    complete = True

    if "subtract" in r and "subtract" not in CALC.lower():
        hallucination.append("subtract")
        correct = False
    if "multiply" in r and "multiply" not in CALC.lower():
        hallucination.append("multiply")
        correct = False
    if "divide" in r and "divide" not in CALC.lower():
        hallucination.append("divide")
        correct = False
    if "factorial" in r:
        hallucination.append("factorial")
        correct = False

    if "what is the output" in question.lower():
        if "30" not in response:
            correct = False

    # Check truncation
    stripped = response.rstrip()
    if stripped and not stripped.endswith((".", "!", "?", "`", "}", "]", ")", '"')):
        last_word = stripped.split()[-1] if stripped.split() else ""
        if len(last_word) > 2:
            complete = False

    return correct, hallucination, complete

model = OLLAMA_MODEL
print(f"Model: {model}")
print(f"Size: 1.3 GB, Quantization: Q8_0")

results = []

# Normal chat
for q in ["What is Python?", "What is 2+2?"]:
    agent = Agent()
    result = agent.run(q, chat_id=1, user_id=1)
    text, ttft, total, tokens, tokps, timing = run(model, result["prompt"])
    correct, hall, complete = evaluate(text, q)
    print(f"\n  NORMAL: '{q}'")
    print(f"    TTFT={ttft:.0f}ms total={total:.0f}ms tokens={tokens} tok/s={tokps:.1f}")
    print(f"    prompt_eval={timing['prompt_eval_count']} eval_count={timing['eval_count']}")
    print(f"    load_duration={timing['load_duration']:.3f}s")
    print(f"    correct={correct} complete={complete} hallucination={hall}")
    print(f"    response: {text[:150]!r}")
    results.append((model, q, ttft, total, tokens, tokps, correct, complete, hall))

# RAG
user_id = 9901
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

for q in ["What is the output?", "Explain this code", "What does this code do?"]:
    agent = Agent()
    result = agent.run(q, chat_id=chat_id, user_id=user_id)
    text, ttft, total, tokens, tokps, timing = run(model, result["prompt"])
    correct, hall, complete = evaluate(text, q)
    print(f"\n  RAG: '{q}'")
    print(f"    TTFT={ttft:.0f}ms total={total:.0f}ms tokens={tokens} tok/s={tokps:.1f}")
    print(f"    prompt_eval={timing['prompt_eval_count']} eval_count={timing['eval_count']}")
    print(f"    load_duration={timing['load_duration']:.3f}s")
    print(f"    correct={correct} complete={complete} hallucination={hall}")
    print(f"    response: {text[:200]!r}")
    results.append((model, q, ttft, total, tokens, tokps, correct, complete, hall))

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# Table
print("\n\n" + "=" * 95)
print(f"{'Model':<15} | {'Request':<25} | {'TTFT':>8} | {'Total':>8} | {'Tok':>5} | {'tok/s':>7} | {'Correct':>8} | {'Complete':>10} | {'Hallucination':>15}")
print("-" * 95)
for r in results:
    print(f"{r[0]:<15} | {r[1]:<25} | {r[2]:>7.0f}ms | {r[3]:>7.0f}ms | {r[4]:>4} | {r[5]:>6.1f} | {str(r[6]):>8} | {str(r[7]):>10} | {','.join(r[8]) or 'none':>15}")

with open(os.path.join(os.path.dirname(__file__), "diag_model_bench.json"), "w") as f:
    json.dump([{"model": r[0], "request": r[1], "ttft": r[2], "total": r[3], "tokens": r[4],
                "tok_per_sec": r[5], "correct": r[6], "complete": r[7], "hallucination": r[8]} for r in results], f, indent=2)
print("\nSaved to diag_model_bench.json")