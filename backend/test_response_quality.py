import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from gemini import ask_gemini

agent = Agent()

print("=" * 70)
print("AGENT RESPONSE QUALITY TESTS")
print("=" * 70)

prompts = [
    "What is a variable in Python?",
    "Explain recursion in C with an example.",
    "Difference between SQL and NoSQL.",
    "My Python program gives a NameError. How do I fix it?",
    "Explain normalization in DBMS for 10 marks.",
    "Write a Java program for method overloading.",
    "Summarize the uploaded document.",
    "Analyze this uploaded Python file.",
]

# Create a temporary file for RAG tests (prompts 7 and 8)
tmp_path = None
try:
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write("""
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)

print(factorial(5))
""")
        tmp_path = f.name

    # Ingest into RAG for user_id=1
    from rag import process_text_file
    process_text_file(tmp_path, 1)
except Exception as e:
    print(f"Warning: could not prepare RAG test file: {e}")

for i, prompt in enumerate(prompts, 1):
    print(f"\n{'=' * 70}")
    print(f"TEST {i}: {prompt}")
    print("=" * 70)

    result = agent.run(prompt, chat_id=1, user_id=1)

    print(f"Action detected: {result['action']}")
    print(f"Tool results present: {bool(result.get('tool_results'))}")
    print(f"RAG context present: {bool(result.get('context'))}")
    print(f"Memories used: {len(result.get('memories', []))}")

    try:
        answer = ask_gemini(result["prompt"])
    except Exception as e:
        answer = f"[Gemini Error: {e}]"

    print(f"\nResponse length: {len(answer)} chars")
    print(f"Has code fences: {'```' in answer}")
    print(f"Has Markdown headers: {'#' in answer}")
    print(f"Has bullet points: {'-' in answer or '*' in answer}")

    print(f"\n--- Response ---\n{answer}\n--- End ---")

    # Basic automated checks
    checks = []
    checks.append(("Non-empty", len(answer.strip()) > 0))
    checks.append(("Not just error", not answer.strip().startswith("Gemini Error")))
    checks.append(("Reasonable length", 50 < len(answer) < 8000))

    if "code" in prompt.lower() or "program" in prompt.lower() or "example" in prompt.lower():
        checks.append(("Contains code fences", "```" in answer))
    if "difference" in prompt.lower() or "compare" in prompt.lower():
        checks.append(("Uses structure", "|" in answer or "#" in answer))
    if "summarize" in prompt.lower() or "analyze" in prompt.lower():
        checks.append(("References document context", result.get("context") is not None or "document" in answer.lower() or "file" in answer.lower()))

    print("\nAutomated checks:")
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

if tmp_path and os.path.exists(tmp_path):
    os.unlink(tmp_path)

print("\n" + "=" * 70)
print("QUALITY TESTS COMPLETE")
print("=" * 70)
