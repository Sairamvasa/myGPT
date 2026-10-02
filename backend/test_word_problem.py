"""Focused tests for _extract_word_problem() and the Python-action branch."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import _extract_word_problem, Agent
from agents.tools import execute_python


def check(label, actual, expected):
    if actual == expected:
        print(f"  PASS: {label}")
        return True
    else:
        print(f"  FAIL: {label}")
        print(f"        Expected: {expected!r}")
        print(f"        Got:      {actual!r}")
        return False


def run_tests():
    PASS = 0
    FAIL = 0

    print("=" * 70)
    print("WORD-PROBLEM PARSER TESTS")
    print("=" * 70)

    # --- Subtraction phrasings ---
    print("\n--- Subtraction ---")
    if check("If I have 5 apples and give away 2, how many remain?",
             _extract_word_problem("If I have 5 apples and give away 2, how many remain?"),
             "5 - 2"):
        PASS += 1
    else:
        FAIL += 1

    if check("I have 10 apples and give away 3. How many remain?",
             _extract_word_problem("I have 10 apples and give away 3. How many remain?"),
             "10 - 3"):
        PASS += 1
    else:
        FAIL += 1

    if check("There are 20 items and I remove 5.",
             _extract_word_problem("There are 20 items and I remove 5."),
             "20 - 5"):
        PASS += 1
    else:
        FAIL += 1

    if check("Start with 10 and subtract 4.",
             _extract_word_problem("Start with 10 and subtract 4."),
             "10 - 4"):
        PASS += 1
    else:
        FAIL += 1

    if check("I have 15 and give away 6.",
             _extract_word_problem("I have 15 and give away 6."),
             "15 - 6"):
        PASS += 1
    else:
        FAIL += 1

    if check("7 apples and give away 2.",
             _extract_word_problem("7 apples and give away 2."),
             "7 - 2"):
        PASS += 1
    else:
        FAIL += 1

    # --- Addition phrasings ---
    print("\n--- Addition ---")
    if check("I have 5 apples and get 3 more.",
             _extract_word_problem("I have 5 apples and get 3 more."),
             "5 + 3"):
        PASS += 1
    else:
        FAIL += 1

    if check("Start with 10 and add 5.",
             _extract_word_problem("Start with 10 and add 5."),
             "10 + 5"):
        PASS += 1
    else:
        FAIL += 1

    # --- Multiplication phrasings ---
    print("\n--- Multiplication ---")
    if check("What is 3 times 4?",
             _extract_word_problem("What is 3 times 4?"),
             "3 * 4"):
        PASS += 1
    else:
        FAIL += 1

    if check("3 groups of 4.",
             _extract_word_problem("3 groups of 4."),
             "3 * 4"):
        PASS += 1
    else:
        FAIL += 1

    # --- Explicit expressions (should NOT be handled by word-problem parser) ---
    print("\n--- Explicit expressions (not word problems) ---")
    if check("What is 27 * 43?",
             _extract_word_problem("What is 27 * 43?"),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("Calculate 15% of 850",
             _extract_word_problem("Calculate 15% of 850"),
             None):
        PASS += 1
    else:
        FAIL += 1

    # --- Programming questions with numbers (must NOT be treated as word problems) ---
    print("\n--- Programming context (must return None) ---")
    if check("What does * mean in Python?",
             _extract_word_problem("What does * mean in Python?"),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("Explain 27 * 43 in this code.",
             _extract_word_problem("Explain 27 * 43 in this code."),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("How do I use a for loop in Python?",
             _extract_word_problem("How do I use a for loop in Python?"),
             None):
        PASS += 1
    else:
        FAIL += 1

    # --- Malformed / ambiguous input (must fall back safely) ---
    print("\n--- Malformed / ambiguous (must return None) ---")
    if check("What comes next: 2, 4, 8, 16, ?",
             _extract_word_problem("What comes next: 2, 4, 8, 16, ?"),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("How many apples do you have?",
             _extract_word_problem("How many apples do you have?"),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("",
             _extract_word_problem(""),
             None):
        PASS += 1
    else:
        FAIL += 1

    if check("hello",
             _extract_word_problem("hello"),
             None):
        PASS += 1
    else:
        FAIL += 1

    # --- End-to-end: Agent.run() with word problem ---
    print("\n--- End-to-end: Agent.run() ---")
    agent = Agent()

    result = agent.run("If I have 5 apples and give away 2, how many remain?", chat_id=9999, user_id=8888)
    print(f"  Action: {result['action']}")
    print(f"  Tool results: {result['tool_results'][:200]}")
    print(f"  Direct answer: {result['answer']}")

    if result["action"] == "python" and result["answer"] is not None:
        if check("Agent.run() direct_answer", result["answer"], "3"):
            PASS += 1
        else:
            FAIL += 1
    else:
        FAIL += 1
        print(f"  FAIL: Agent.run() did not produce direct_answer=3")
        print(f"         action={result['action']}, answer={result['answer']}")

    # Verify the expression was extracted correctly
    if "5 - 2" in result.get("tool_results", ""):
        PASS += 1
        print(f"  PASS: tool_results contains '5 - 2'")
    else:
        FAIL += 1
        print(f"  FAIL: tool_results does not contain '5 - 2'")

    # --- End-to-end: explicit expression still works ---
    print("\n--- End-to-end: explicit expression ---")
    result2 = agent.run("What is 27 * 43?", chat_id=9999, user_id=8888)
    print(f"  Action: {result2['action']}")
    print(f"  Direct answer: {result2['answer']}")
    if result2["action"] == "python" and result2["answer"] is not None:
        if check("Explicit expression direct_answer", result2["answer"], "1161"):
            PASS += 1
        else:
            FAIL += 1
    else:
        FAIL += 1
        print(f"  FAIL: explicit expression not handled")

    # --- End-to-end: programming question stays safe ---
    print("\n--- End-to-end: programming question ---")
    result3 = agent.run("What does * mean in Python?", chat_id=9999, user_id=8888)
    print(f"  Action: {result3['action']}")
    # Should be chat (planner routes it), not python
    if result3["action"] == "chat":
        PASS += 1
        print(f"  PASS: programming question stays chat")
    else:
        FAIL += 1
        print(f"  FAIL: programming question routed to {result3['action']}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    if FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{FAIL} TEST(S) FAILED")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())