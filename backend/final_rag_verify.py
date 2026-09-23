"""Final verification: RAG actually used with relevance threshold."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide
from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options, get_num_predict
from rag import process_text_file, search_pdf, RAG_RELEVANCE_THRESHOLD, vector_stores, _load_user_state

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

# Setup
user_id = 9911
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

_load_user_state(user_id)
vs = vector_stores.get(user_id)

print("=" * 80)
print("FINAL RAG VERIFICATION")
print("=" * 80)
print("RAG_RELEVANCE_THRESHOLD = " + str(RAG_RELEVANCE_THRESHOLD))
print("Distance strategy: EUCLIDEAN (LOWER = more relevant)")
print("Model: " + OLLAMA_MODEL)

questions = [
    "What is the output?",
    "Explain this code",
    "What does this code do?",
    "What is the capital of France?",
]

for question in questions:
    print("\n" + "=" * 80)
    print("QUESTION: " + repr(question))
    print("=" * 80)

    # 1. Planner action
    action = decide(question)
    print("  Planner action: " + action)

    # 2. FAISS score
    docs_and_scores = vs.similarity_search_with_score(question, k=5)
    best_score = docs_and_scores[0][1] if docs_and_scores else float("inf")
    print("  FAISS best score: " + str(round(best_score, 4)))
    print("  Threshold: " + str(RAG_RELEVANCE_THRESHOLD))
    score_ok = best_score <= RAG_RELEVANCE_THRESHOLD
    print("  Score <= threshold: " + str(score_ok))

    # 3. RAG context accepted/rejected
    agent = Agent()
    t0 = time.perf_counter()
    result = agent.run(question, chat_id=chat_id, user_id=user_id)
    t_agent = (time.perf_counter() - t0) * 1000

    rag_used = result.get("context") is not None
    print("  RAG context accepted: " + str(rag_used))
    print("  Agent action: " + result["action"])

    if rag_used:
        has_calc = "def add(a, b)" in result["context"] and "print(x)" in result["context"]
        print("  calculator.py in prompt: " + str(has_calc))
        print("  Context length: " + str(len(result["context"])) + " chars")
    else:
        print("  calculator.py in prompt: N/A (RAG rejected)")

    # 4. Final answer via Ollama
    prompt = result["prompt"]
    num_predict = get_num_predict(result.get("action", "chat"), question)
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
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
            break
    t_total = (time.perf_counter() - t0) * 1000

    print("  RAG used: " + str(rag_used))
    print("  num_predict: " + str(num_predict))
    print("  TTFT: " + str(round(t_first)) + "ms")
    print("  Total: " + str(round(t_total)) + "ms")
    print("  Final answer: " + repr(total_text[:200]))

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)