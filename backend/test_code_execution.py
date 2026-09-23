"""Focused tests for code-execution routing in planner.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide

PASS = 0
FAIL = 0

def check(question, expected, label):
    global PASS, FAIL
    actual = decide(question)
    if actual == expected:
        PASS += 1
        print(f"  PASS: {label}")
    else:
        FAIL += 1
        print(f"  FAIL: {label}")
        print(f"        Question: {question[:60]!r}...")
        print(f"        Expected: {expected}, Got: {actual}")

print("=" * 70)
print("CODE-EXECUTION ROUTING TESTS")
print("=" * 70)

# --- Should route to python ---
print("\n--- Should route to python ---")
check("What is the output of:\nx = 10\ny = 20\nprint(x + y)",
      "python", "what is the output of + code")

check("Run this Python code:\nx = 10\ny = 20\nprint(x + y)",
      "python", "run this python code")

check("Execute:\nx = 10\ny = 20\nprint(x + y)",
      "python", "execute + code")

check("What does this Python code output?\nx = 10\ny = 20\nprint(x + y)",
      "python", "what does this python code output")

check("```python\nx = 10\ny = 20\nprint(x + y)\n```",
      "python", "fenced python block")

check("What is the output of:\ndef add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)",
      "python", "what is the output of + function definition")

# --- Should NOT route to python (preserve RAG for document questions) ---
print("\n--- Should NOT route to python ---")
check("What is the output?",
      "general_knowledge", "what is the output (no code, general knowledge)")

check("What is the output of the document?",
      "rag", "what is the output of the document (RAG)")

# --- Should stay chat (programming explanation, not execution) ---
print("\n--- Should stay chat (explanation, not execution) ---")
check("What does * mean in Python?",
      "chat", "operator explanation")

check("Explain 27 * 43 in this code.",
      "chat", "explain code with numbers")

# --- Existing routing must not regress ---
print("\n--- Existing routing (no regression) ---")
check("What is 27 * 43?", "python", "arithmetic expression")
check("What is the capital of Andhra Pradesh?", "web", "fresh factual")
check("What is the weather today?", "current_info", "weather -> current_info")
check("What time is it?", "time", "time")
check("Explain this code", "code_explanation", "code explanation keyword")
check("hi", "chat", "greeting")
check("What comes next: 2, 4, 8, 16, ?", "chat", "sequence stays chat")

# --- Summary ---
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
if FAIL == 0:
    print("ALL CODE-EXECUTION TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)