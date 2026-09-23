"""Investigation: RAG code output quality root cause analysis."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from agents.planner import decide
from llm import (
    OLLAMA_MODEL, OLLAMA_TEMPERATURE, OLLAMA_TOP_P, OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT, OLLAMA_KEEP_ALIVE,
    _get_client, _chat_messages, _generation_options, get_num_predict
)
from rag import process_text_file, search_pdf, RAG_RELEVANCE_THRESHOLD, vector_stores, _load_user_state
from agents.prompt_builder import build_prompt

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

client = _get_client()

def get_full_prompt(question, user_id=None, chat_id=None):
    """Get the exact prompt that would be sent to Ollama."""
    agent = Agent()
    result = agent.run(question, chat_id=chat_id, user_id=user_id)
    return result

def run_experiment(name, prompt, num_predict, temperature=None, top_p=None):
    """Run a single experiment and return results."""
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    timing = {}
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=True,
        options={
            **_generation_options(num_predict),
            "temperature": temperature if temperature is not None else OLLAMA_TEMPERATURE,
            "top_p": top_p if top_p is not None else OLLAMA_TOP_P,
        },
        keep_alive=OLLAMA_KEEP_ALIVE,
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
    return total_text, t_first, total, tokens, tok_per_sec

def evaluate_correctness(response, question):
    r = response.lower()
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
    if "divide" in r and "divide" not in CALC.lower():
        hall.append("divide")
        correct = False
    if "what is the output" in question.lower() and "30" not in text:
        correct = False
    if "what is 2+2" in question.lower() and "4" not in text:
        correct = False
    stripped = text.rstrip()
    if stripped and not stripped.endswith((".", "!", "?", "`", "}", "]", ")", '"', ":", "-")):
        if len(stripped.split()[-1]) > 2:
            complete = False
    return correct, hall, complete

# Setup
CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9999
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

# 1. Exact calculator.py text stored in RAG
print("=" * 80)
print("1. EXACT CALCULATOR.PY TEXT STORED IN RAG")
print("=" * 80)
print(repr(CALC))

# 2. Exact retrieved context
print("\n" + "=" * 80)
print("2. EXACT RETRIEVED CONTEXT FROM RAG")
print("=" * 80)
from rag import vector_stores, uploaded_files_map, process_text_file
_load_user_state(9999)  # Use fresh user_id to avoid conflicts
user_id = 9999
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

vs = vector_stores.get(user_id)
docs_and_scores = vs.similarity_search_with_score("What is the output?", k=5)
print("Best FAISS score:", docs_and_scores[0][1] if docs_and_scores else "N/A")
for i, (doc, score) in enumerate(docs_and_scores[:3]):
    print(f"  Result {i}: score={score:.4f}, source={doc.metadata.get('source')}")
    print(f"  Content: {repr(doc.page_content)}")

# 3. Exact final user prompt sent to Ollama
print("\n" + "=" * 80)
print("3. EXACT FINAL USER PROMPT SENT TO OLLAMA")
print("=" * 80)
agent = Agent()
result = agent.run("What is the output?", chat_id=1, user_id=user_id)
prompt = result["prompt"]
print("Action:", result["action"])
print("RAG context accepted:", result["context"] is not None)
print("num_predict:", get_num_predict(result["action"], "What is the output?"))
print("\n--- FULL PROMPT ---")
print(prompt)

# 4. Exact system prompt
print("\n" + "=" * 80)
print("4. EXACT SYSTEM PROMPT")
print("=" * 80)
from agents.prompts import SYSTEM_PROMPT
print(SYSTEM_PROMPT)

# 5. Whether any previous conversation/history is included
print("\n" + "=" * 80)
print("5. HISTORY/MEMORY INCLUSION")
print("=" * 80)
result = agent.run("What is the output?", chat_id=1, user_id=user_id)
print("History included:", result["history"] is not None and len(result["history"]) > 0)
print("Memories included:", result["memories"] is not None and len(result["memories"]) > 0)
print("Tool results:", result["tool_results"])
print("Context present:", result["context"] is not None)

# 6. Ollama options
print("\n" + "=" * 80)
print("6. OLLAMA OPTIONS")
print("=" * 80)
from llm import OLLAMA_TEMPERATURE, OLLAMA_TOP_P, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_KEEP_ALIVE
print(f"  temperature: {OLLAMA_TEMPERATURE}")
print(f"  top_p: {OLLAMA_TOP_P}")
print(f"  num_predict: {OLLAMA_NUM_PREDICT}")
print(f"  num_ctx: {OLLAMA_NUM_CTX}")
print(f"  keep_alive: {OLLAMA_KEEP_ALIVE}")

# 6b. Whether the model receives the code once or multiple times
print("\n" + "=" * 80)
print("6b. CODE DUPLICATION CHECK")
print("=" * 80)
# Check if calculator.py content appears multiple times in prompt
code_occurrences = prompt.count("def add(a, b)")
print(f"  'def add(a, b)' appears {code_occurrences} times in prompt")

# 7. Whether any prompt formatting could confuse the model
print("\n" + "=" * 80)
print("7. PROMPT FORMATTING ANALYSIS")
print("=" * 80)
# Print the prompt sections
sections = prompt.split("\n\n---\n\n")
for i, section in enumerate(sections):
    print(f"  Section {i}: {section[:80]}...")

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)