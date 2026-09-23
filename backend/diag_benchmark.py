"""Benchmark num_predict values: 160, 256, 384, 512 against calculator.py."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages
from rag import process_text_file
from database import save_message, get_history

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

client = _get_client()

def ask(prompt, num_predict):
    t0 = time.perf_counter()
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=False,
        options={"temperature": 0.2, "top_p": 0.9, "num_ctx": 4096, "num_predict": num_predict},
        keep_alive="10m",
    )
    dt = (time.perf_counter() - t0) * 1000
    text = resp.get("message", {}).get("content", "").strip()
    # Count tokens roughly
    tokens = len(text.split())
    return text, dt, tokens

def setup_rag(user_id):
    rag_dir = os.path.join("rag_indexes", str(user_id))
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(CALC)
        tmp = f.name
    process_text_file(tmp, user_id, source_filename="calculator.py")
    os.unlink(tmp)
    return rag_dir

def cleanup(rag_dir):
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

def evaluate(response, question):
    """Evaluate response quality."""
    r = response.lower()
    correct = True
    hallucination = []
    complete = True
    notes = []

    # Check for hallucinated functions not in calculator.py
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

    # Check for correct output
    if "what is the output" in question.lower() or "output" in question.lower():
        if "30" not in response:
            correct = False
            notes.append("missing 30")

    # Check for truncation (response ends mid-word or mid-sentence)
    if response and not response.endswith((".", "!", "?", "`", "}", "]", ")")):
        # Check if it ends with a complete word
        last_word = response.split()[-1] if response.split() else ""
        if len(last_word) > 2 and not last_word.endswith((".", ",")):
            complete = False
            notes.append("possibly truncated")

    return correct, hallucination, complete, notes

# Benchmark values
values = [160, 256, 384, 512]
questions = ["What is the output?", "Explain this code", "What does this code do?"]

results = []

for num_predict in values:
    print(f"\n{'='*70}")
    print(f"NUM_PREDICT = {num_predict}")
    print(f"{'='*70}")

    user_id = 9700 + num_predict
    chat_id = 1
    rag_dir = setup_rag(user_id)

    # Populate chat history with factorial content to simulate the real scenario
    for i in range(4):
        if i % 2 == 0:
            save_message(chat_id, "user", "factorial program")
        else:
            save_message(chat_id, "assistant", "Here is the factorial program...")

    agent = Agent()

    for question in questions:
        result = agent.run(question, chat_id=chat_id, user_id=user_id)
        text, dt, tokens = ask(result["prompt"], num_predict)
        correct, hallucination, complete, notes = evaluate(text, question)

        print(f"\n  Q: {question}")
        print(f"  Time: {dt:.0f}ms | Tokens: {tokens} | Complete: {complete} | Correct: {correct}")
        if hallucination:
            print(f"  Hallucinations: {hallucination}")
        if notes:
            print(f"  Notes: {notes}")
        print(f"  Response: {text[:200]}...")

        results.append({
            "num_predict": num_predict,
            "question": question,
            "time_ms": round(dt),
            "tokens": tokens,
            "complete": complete,
            "correct": correct,
            "hallucination": hallucination,
            "notes": notes,
            "response": text,
        })

    cleanup(rag_dir)

# Print comparison table
print("\n\n" + "=" * 100)
print("COMPARISON TABLE")
print("=" * 100)
print(f"{'num_predict':>12} | {'question':<25} | {'time':>8} | {'tokens':>7} | {'complete':>9} | {'correct':>8} | {'hallucination':>15}")
print("-" * 100)
for r in results:
    print(f"{r['num_predict']:>12} | {r['question']:<25} | {r['time_ms']:>7}ms | {r['tokens']:>6} | {str(r['complete']):>9} | {str(r['correct']):>8} | {','.join(r['hallucination']) or 'none':>15}")

# Save results
with open(os.path.join(os.path.dirname(__file__), "diag_benchmark.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nResults saved to diag_benchmark.json")