"""User-facing benchmark: compare smart num_predict vs fixed 160."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options, get_num_predict
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def run(prompt, num_predict):
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    timing = {}
    for resp in client.chat(
        model=OLLAMA_MODEL,
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
            timing["eval_count"] = resp.get("eval_count", 0)
            timing["eval_duration"] = resp.get("eval_duration", 0) / 1e9
    total = (time.perf_counter() - t0) * 1000
    tokens = len(total_text.split())
    tok_per_sec = tokens / timing["eval_duration"] if timing.get("eval_duration") else 0
    return total_text, t_first, total, tokens, tok_per_sec, timing

# Setup RAG
user_id = 9971
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

agent = Agent()

print("=" * 80)
print("BEFORE vs AFTER: Smart num_predict vs Fixed 160")
print("=" * 80)

# Test each question with both fixed 160 and smart num_predict
questions = [
    ("Normal: What is 2+2?", "What is 2+2?", None, None),
    ("Normal: What is Python?", "What is Python?", None, None),
    ("RAG: What is the output?", "What is the output?", user_id, chat_id),
    ("RAG: Explain this code", "Explain this code", user_id, chat_id),
    ("RAG: What does this code do?", "What does this code do?", user_id, chat_id),
]

print("\n" + "-" * 80)
print(f"{'Question':<30} | {'Limit':>6} | {'TTFT':>8} | {'Total':>8} | {'Tokens':>7} | {'tok/s':>6} | {'Complete':>9} | {'Correct':>8} | {'Halluc':>8}")
print("-" * 80)

for name, question, uid, cid in questions:
    result = agent.run(question, chat_id=cid, user_id=uid)
    prompt = result["prompt"]
    action = result.get("action", "chat")
    smart_limit = get_num_predict(action, question)

    # Run with fixed 160
    text160, ttft160, total160, tok160, tps160, timing160 = run(prompt, 160)
    # Run with smart limit
    text_smart, ttft_smart, total_smart, tok_smart, tps_smart, timing_smart = run(prompt, smart_limit)

    # Evaluate
    def evaluate(text, q):
        r = text.lower()
        correct = True
        hall = []
        complete = True
        if "factorial" in r:
            hall.append("factorial")
            correct = False
        if "subtract" in r and "subtract" not in CALC.lower():
            hall.append("subtract")
            correct = False
        if "multiply" in r and "multiply" not in CALC.lower():
            hall.append("multiply")
            correct = False
        if "what is the output" in q.lower() and "30" not in text:
            correct = False
        if "what is 2+2" in q.lower() and "4" not in text:
            correct = False
        stripped = text.rstrip()
        if stripped and not stripped.endswith((".", "!", "?", "`", "}", "]", ")")):
            if len(stripped.split()[-1]) > 2:
                complete = False
        return correct, hall, complete

    c160, h160, comp160 = evaluate(text160, question)
    csmart, hsmart, compsmart = evaluate(text_smart, question)

    print(f"{name:<30} | {160:>6} | {ttft160:>7.0f}ms | {total160:>7.0f}ms | {tok160:>6} | {tps160:>5.1f} | {str(comp160):>9} | {str(c160):>8} | {','.join(h160) or 'none':>8}")
    print(f"{'':<30} | {smart_limit:>6} | {ttft_smart:>7.0f}ms | {total_smart:>7.0f}ms | {tok_smart:>6} | {tps_smart:>5.1f} | {str(compsmart):>9} | {str(csmart):>8} | {','.join(hsmart) or 'none':>8}")

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("Smart num_predict applies different limits based on action and message content:")
print("  - Short math/factual: 64 tokens")
print("  - Normal chat: 160 tokens")
print("  - RAG/code analysis: 320 tokens")
print("  - Long analysis: 512 tokens")
print("  - Environment OLLAMA_NUM_PREDICT caps all results")