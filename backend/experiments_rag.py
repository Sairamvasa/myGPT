"""Experiment script for RAG output quality investigation."""
import os
import sys
import time
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file
from agents.agent import Agent

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

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

client = _get_client()

def ask(prompt, num_predict=160, temperature=0.2, top_p=0.9, stream=False):
    t0 = time.perf_counter()
    t_first = None
    text = ""
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
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

agent = Agent()
result = agent.run("What is the output?", chat_id=chat_id, user_id=user_id)
full_prompt = result["prompt"]

print("=" * 80)
print("BASELINE: Current production prompt")
print("=" * 80)
print(f"Prompt length: {len(full_prompt)} chars")
print(f"\n--- FULL PROMPT ---")
print(full_prompt)
print(f"\n--- END PROMPT ---\n")

answer, ttft, total, eval_count, prompt_eval_count = ask(full_prompt)
print(f"Answer: {answer!r}")
print(f"TTFT: {ttft:.0f}ms")
print(f"Total: {total:.0f}ms")
print(f"Eval tokens: {eval_count}")
print(f"Prompt tokens: {prompt_eval_count}")
print(f"Correct (30): {'30' in answer}")
print()

# Experiment A: Minimal prompt with just the code and question
print("=" * 80)
print("EXPERIMENT A: Minimal prompt - code + question only")
print("=" * 80)
prompt_a = f"""Here is some code:

```python
{CALC}
```

What is the output of this code?"""
print(f"Prompt:\n{prompt_a}\n")
answer, ttft, total, eval_count, prompt_eval_count = ask(prompt_a)
print(f"Answer: {answer!r}")
print(f"TTFT: {ttft:.0f}ms")
print(f"Total: {total:.0f}ms")
print(f"Eval tokens: {eval_count}")
print(f"Prompt tokens: {prompt_eval_count}")
print(f"Correct (30): {'30' in answer}")
print()

# Experiment B: More explicit instruction
print("=" * 80)
print("EXPERIMENT B: Explicit instruction")
print("=" * 80)
prompt_b = f"""Read the code carefully. Do not infer a different example. What exact value
is printed by print(x)?

Code:
```python
{CALC}
```"""
print(f"Prompt:\n{prompt_b}\n")
answer, ttft, total, eval_count, prompt_eval_count = ask(prompt_b)
print(f"Answer: {answer!r}")
print(f"TTFT: {ttft:.0f}ms")
print(f"Total: {total:.0f}ms")
print(f"Eval tokens: {eval_count}")
print(f"Prompt tokens: {prompt_eval_count}")
print(f"Correct (30): {'30' in answer}")
print()

# Experiment C: Direct calculation
print("=" * 80)
print("EXPERIMENT C: Direct calculation request")
print("=" * 80)
prompt_c = f"""Calculate add(10, 20). Return only the numeric output.

def add(a, b):
    return a + b"""
print(f"Prompt:\n{prompt_c}\n")
answer, ttft, total, eval_count, prompt_eval_count = ask(prompt_c)
print(f"Answer: {answer!r}")
print(f"TTFT: {ttft:.0f}ms")
print(f"Total: {total:.0f}ms")
print(f"Eval tokens: {eval_count}")
print(f"Prompt tokens: {prompt_eval_count}")
print(f"Correct (30): {'30' in answer}")
print()

# Experiment D: Same prompt but temperature=0
print("=" * 80)
print("EXPERIMENT D: Production prompt with temperature=0")
print("=" * 80)
answer, ttft, total, eval_count, prompt_eval_count = ask(full_prompt, temperature=0.0)
print(f"Answer: {answer!r}")
print(f"TTFT: {ttft:.0f}ms")
print(f"Total: {total:.0f}ms")
print(f"Eval tokens: {eval_count}")
print(f"Prompt tokens: {prompt_eval_count}")
print(f"Correct (30): {'30' in answer}")
print()

# Experiment E: Run same question 3 times
print("=" * 80)
print("EXPERIMENT E: Consistency check (3 runs)")
print("=" * 80)
for i in range(3):
    answer, ttft, total, eval_count, prompt_eval_count = ask(full_prompt)
    print(f"Run {i+1}: {answer!r} | TTFT={ttft:.0f}ms | Total={total:.0f}ms | Correct={'30' in answer}")

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)