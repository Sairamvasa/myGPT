"""Benchmark num_predict values: 64, 96, 128, 160 against same requests."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def run(model, prompt, num_predict):
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    timing = {}
    for resp in client.chat(
        model=model,
        messages=_chat_messages(prompt),
        stream=True,
        options={"temperature": 0.2, "top_p": 0.9, "num_ctx": 4096, "num_predict": num_predict},
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
            timing["prompt_eval_count"] = resp.get("prompt_eval_count", 0)
            timing["total_duration"] = resp.get("total_duration", 0) / 1e9
    total = (time.perf_counter() - t0) * 1000
    tokens = len(total_text.split())
    tok_per_sec = tokens / timing["eval_duration"] if timing.get("eval_duration") else 0
    return total_text, t_first, total, tokens, tok_per_sec, timing

def evaluate(response, question, num_predict):
    r = response.lower()
    correct = True
    hallucination = []
    complete = True
    notes = []

    # Check for hallucinated functions
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

    # Check correctness per question
    if "what is the output" in question.lower():
        if "30" not in response:
            correct = False
            notes.append("missing 30")

    if "what is 2+2" in question.lower():
        if "4" not in response:
            correct = False
            notes.append("missing 4")

    # Check truncation
    stripped = response.rstrip()
    if stripped and not stripped.endswith((".", "!", "?", "`", "}", "]", ")", '"', ":", "-")):
        last_word = stripped.split()[-1] if stripped.split() else ""
        if len(last_word) > 2:
            complete = False
            notes.append("possibly truncated")

    # Check if it stopped naturally before the limit
    # If eval_count < num_predict, the model stopped naturally
    # We check this in the caller via timing

    return correct, hallucination, complete, notes

# Setup RAG
user_id = 9981
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

# Test matrix
limits = [64, 96, 128, 160]
questions = [
    ("Normal: What is 2+2?", "What is 2+2?", None, None),
    ("Normal: What is Python?", "What is Python?", None, None),
    ("RAG: What is the output?", "What is the output?", user_id, chat_id),
    ("RAG: Explain this code", "Explain this code", user_id, chat_id),
    ("RAG: What does this code do?", "What does this code do?", user_id, chat_id),
]

results = []

for num_predict in limits:
    print("\n" + "=" * 70)
    print("NUM_PREDICT = " + str(num_predict))
    print("=" * 70)
    for name, question, uid, cid in questions:
        result = agent.run(question, chat_id=cid, user_id=uid)
        prompt = result["prompt"]
        text, ttft, total, tokens, tokps, timing = run(OLLAMA_MODEL, prompt, num_predict)
        correct, hall, complete, notes = evaluate(text, question, num_predict)
        stopped_naturally = timing["eval_count"] < num_predict

        print("  " + name + ":")
        print("    TTFT=" + str(round(ttft)) + "ms total=" + str(round(total)) + "ms tokens=" + str(tokens) + " tok/s=" + str(round(tokps, 1)))
        print("    eval_count=" + str(timing["eval_count"]) + " stopped_naturally=" + str(stopped_naturally))
        print("    complete=" + str(complete) + " correct=" + str(correct) + " hall=" + str(hall))
        if notes:
            print("    notes=" + str(notes))
        print("    response=" + repr(text[:150]))

        results.append({
            "num_predict": num_predict,
            "name": name,
            "question": question,
            "ttft": round(ttft),
            "total": round(total),
            "tokens": tokens,
            "tok_per_sec": round(tokps, 1),
            "eval_count": timing["eval_count"],
            "complete": complete,
            "correct": correct,
            "hallucination": hall,
            "notes": notes,
            "stopped_naturally": stopped_naturally,
            "response": text,
        })

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# Print summary table
print("\n\n" + "=" * 100)
print("SUMMARY TABLE")
print("=" * 100)
print("Limit | Question | TTFT | Total | Tokens | tok/s | Complete | Correct | Hallucination | Stopped Naturally")
print("-" * 100)
for r in results:
    print(str(r["num_predict"]) + " | " + r["name"] + " | " + str(r["ttft"]) + "ms | " + str(r["total"]) + "ms | " + str(r["tokens"]) + " | " + str(r["tok_per_sec"]) + " | " + str(r["complete"]) + " | " + str(r["correct"]) + " | " + (",".join(r["hallucination"]) or "none") + " | " + str(r["stopped_naturally"]))

with open(os.path.join(os.path.dirname(__file__), "diag_smart_limits.json"), "w") as f:
    json.dump([{k: v for k, v in r.items() if k != "response"} for r in results], f, indent=2)
print("\nSaved to diag_smart_limits.json")