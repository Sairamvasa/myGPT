"""Measure prompt-size overhead for normal chat and RAG requests."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from agents.prompts import SYSTEM_PROMPT
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def count_tokens(text):
    return len(text.split())

def ollama_stream(prompt, num_predict=160):
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
    total = (time.perf_counter() - t0) * 1000
    return t_first, total, total_text

def measure(name, message, user_id=None, chat_id=None):
    print(f"\n{'='*70}")
    print(f"REQUEST: {name} | message={message!r}")
    print(f"{'='*70}")

    agent = Agent()
    result = agent.run(message, chat_id=chat_id, user_id=user_id)

    action = result["action"]
    context = result.get("context")
    tool_results = result.get("tool_results")
    memories = result.get("memories", [])
    history = result.get("history", [])
    prompt = result["prompt"]

    # Break down prompt sections
    sections = prompt.split("\n\n---\n\n")
    section_sizes = {}
    for s in sections:
        first_line = s.split("\n")[0][:60]
        section_sizes[first_line] = len(s)

    print(f"  Action: {action}")
    print(f"  System prompt size: {len(SYSTEM_PROMPT)} chars, {count_tokens(SYSTEM_PROMPT)} tokens")
    print(f"  User question size: {len(message)} chars, {count_tokens(message)} tokens")
    print(f"  Chat history messages: {len(history)}")
    print(f"  Chat history size: {sum(len(m) for _, m in history)} chars")
    print(f"  Memories: {len(memories)}")
    print(f"  Context present: {context is not None}")
    if context:
        print(f"  Context size: {len(context)} chars, {count_tokens(context)} tokens")
    print(f"  Tool results present: {tool_results is not None}")
    if tool_results:
        print(f"  Tool results size: {len(tool_results)} chars")
    print(f"  Final prompt size: {len(prompt)} chars, {count_tokens(prompt)} tokens")

    print(f"\n  Prompt sections:")
    for k, v in section_sizes.items():
        print(f"    {k}: {v} chars")

    # Run Ollama
    ttft, total, text = ollama_stream(prompt)
    out_tokens = count_tokens(text)

    print(f"\n  Ollama TTFT: {ttft:.1f}ms")
    print(f"  Ollama total: {total:.1f}ms")
    print(f"  Output tokens: {out_tokens}")
    print(f"  Response preview: {text[:150]!r}")

    return {
        "name": name,
        "action": action,
        "prompt_chars": len(prompt),
        "prompt_tokens": count_tokens(prompt),
        "context_chars": len(context) if context else 0,
        "system_chars": len(SYSTEM_PROMPT),
        "history_msgs": len(history),
        "history_chars": sum(len(m) for _, m in history),
        "memories": len(memories),
        "tool_chars": len(tool_results) if tool_results else 0,
        "ttft": round(ttft, 1),
        "gen_time": round(total, 1),
        "out_tokens": out_tokens,
        "response": text,
    }

results = []

# 1. Normal chat
results.append(measure("Normal: What is Python?", "What is Python?"))

# 2. RAG setup
user_id = 9801
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

# 2a. RAG: What is the output?
results.append(measure("RAG: What is the output?", "What is the output?", user_id=user_id, chat_id=chat_id))

# 2b. RAG: Explain this code
results.append(measure("RAG: Explain this code", "Explain this code", user_id=user_id, chat_id=chat_id))

# 2c. RAG: What does this code do?
results.append(measure("RAG: What does this code do?", "What does this code do?", user_id=user_id, chat_id=chat_id))

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# Print summary table
print("\n\n" + "=" * 110)
print("PROMPT SIZE OVERHEAD TABLE")
print("=" * 110)
print(f"{'Request':<30} | {'Action':>8} | {'Prompt Chars':>12} | {'Prompt Tok':>10} | {'Ctx Chars':>10} | {'TTFT':>8} | {'Gen Time':>10} | {'Out Tok':>8}")
print("-" * 110)
for r in results:
    print(f"{r['name']:<30} | {r['action']:>8} | {r['prompt_chars']:>12} | {r['prompt_tokens']:>10} | {r['context_chars']:>10} | {r['ttft']:>7.1f} | {r['gen_time']:>9.1f} | {r['out_tokens']:>7}")

# Analyze overhead
print("\n" + "=" * 70)
print("OVERHEAD ANALYSIS")
print("=" * 70)
sys_chars = len(SYSTEM_PROMPT)
print(f"System prompt (constant): {sys_chars} chars")
for r in results:
    if r["action"] == "rag":
        overhead = r["prompt_chars"] - sys_chars - r["context_chars"] - len(r["name"].split(": ")[-1].strip("'\""))
        print(f"\n  {r['name']}:")
        print(f"    System prompt: {sys_chars} chars")
        print(f"    Context: {r['context_chars']} chars")
        print(f"    History: {r['history_chars']} chars ({r['history_msgs']} msgs)")
        print(f"    Memories: {r['memories']}")
        print(f"    Tool results: {r['tool_chars']} chars")
        print(f"    Total prompt: {r['prompt_chars']} chars")
        # Check for duplication
        if r["context_chars"] > 0:
            calc_content = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)"
            if r["context"].count(calc_content) > 1:
                print(f"    DUPLICATION: calculator.py content appears {r['context'].count(calc_content)} times")
            else:
                print(f"    Duplication: calculator.py content appears once (OK)")

with open(os.path.join(os.path.dirname(__file__), "diag_prompt_size.json"), "w") as f:
    json.dump([{k: v for k, v in r.items() if k != 'response'} for r in results], f, indent=2)
print("\nResults saved to diag_prompt_size.json")