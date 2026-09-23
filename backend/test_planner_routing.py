"""Focused planner routing tests. Tests only decide() output, no execution."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide, ACTION_CHAT, ACTION_PYTHON, ACTION_WEB, ACTION_RAG, ACTION_TIME, ACTION_CODE, ACTION_CODE_EXPLANATION, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH, ACTION_GENERAL_KNOWLEDGE, ACTION_MATH, ACTION_CREATIVE

PASS = 0
FAIL = 0

def check(question, expected, label):
    global PASS, FAIL
    actual = decide(question)
    ok = actual == expected
    if ok:
        PASS += 1
        print(f"  PASS: {label}")
    else:
        FAIL += 1
        print(f"  FAIL: {label}")
        print(f"        Question: {question!r}")
        print(f"        Expected: {expected}, Got: {actual}")

print("=" * 70)
print("FOCUSED PLANNER ROUTING TESTS")
print("=" * 70)

# --- Arithmetic without "calculate" ---
print("\n--- Arithmetic (no keyword) ---")
check("What is 27 * 43?", ACTION_PYTHON, "multiplication without keyword")
check("What is 125 + 378?", ACTION_PYTHON, "addition without keyword")
check("What is 144 / 12?", ACTION_PYTHON, "division without keyword")
check("How much is 99 * 17?", ACTION_PYTHON, "how much is + multiplication")

# --- Arithmetic with "calculate" ---
print("\n--- Arithmetic (with keyword) ---")
check("Calculate 27 * 43", ACTION_PYTHON, "calculate + multiplication")
check("Compute 125 + 378", ACTION_PYTHON, "compute + addition")

# --- Percentage calculation ---
print("\n--- Percentage ---")
check("25% of 800?", ACTION_PYTHON, "percentage calculation")

# --- Subtraction word problem ---
print("\n--- Word problems ---")
check("If I have 5 apples and give away 2, how many remain?", ACTION_PYTHON, "subtraction word problem")

# --- Programming questions with math symbols (must stay chat) ---
print("\n--- Programming context (must stay chat) ---")
check("What does * mean in Python?", ACTION_CHAT, "operator question in Python")
check("Explain 27 * 43 in this code", ACTION_CHAT, "code explanation with numbers")

# --- Sequence question stays chat ---
print("\n--- Sequence / reasoning ---")
check("What comes next: 2, 4, 8, 16, ?", ACTION_CHAT, "sequence question stays chat")

# --- Current/fresh factual routes web ---
print("\n--- Factual: fresh vs stable ---")
check("What is the capital of Andhra Pradesh?", ACTION_WEB, "capital question routes web")
check("What is the population of India?", ACTION_WEB, "population question routes web")
check("Who is the president of India?", ACTION_WEB, "current leader routes web")

# --- Stable factual stays general_knowledge ---
print("\n--- Stable factual (general_knowledge) ---")
check("Who wrote Romeo and Juliet?", ACTION_GENERAL_KNOWLEDGE, "stable literary fact routes general_knowledge")
check("What is the largest ocean?", ACTION_GENERAL_KNOWLEDGE, "stable geographic fact routes general_knowledge")

# --- Code generation routes code ---
print("\n--- Code generation ---")
check("Write a Java program to find GCD of two numbers", ACTION_CODE, "Java GCD code generation")
check("Write a Python script to sort a list", ACTION_CODE, "Python script generation")
check("Generate a function to calculate factorial", ACTION_CODE, "function generation")

# --- Code explanation routes code_explanation ---
print("\n--- Code explanation ---")
check("Explain this code line by line", ACTION_CODE_EXPLANATION, "code explanation line by line")
check("Explain this code", ACTION_CODE_EXPLANATION, "code explanation routes code_explanation")
check("What does this code do?", ACTION_CODE_EXPLANATION, "what does code do routes code_explanation")

# --- Existing RAG routing unchanged ---
print("\n--- RAG routing (unchanged) ---")
check("What is the output?", ACTION_RAG, "output question routes rag")
check("Find any problems in this code", ACTION_RAG, "code review routes rag")

# --- Current info routes current_info ---
print("\n--- Current info routing ---")
check("Today's petrol price in India", ACTION_CURRENT_INFO, "petrol price routes current_info")
check("Current Bitcoin price", ACTION_CURRENT_INFO, "bitcoin price routes current_info")
check("Weather today", ACTION_CURRENT_INFO, "weather today routes current_info")

# --- Web research routes web_research ---
print("\n--- Web research routing ---")
check("Latest AI news", ACTION_WEB_RESEARCH, "latest news routes web_research")
check("Recent developments in AI", ACTION_WEB_RESEARCH, "recent developments routes web_research")

# --- Existing web routing unchanged ---
print("\n--- Web routing (unchanged) ---")
check("What is the weather today?", ACTION_CURRENT_INFO, "weather today routes current_info")
check("What are the latest AI news headlines?", ACTION_WEB_RESEARCH, "latest news headlines routes web_research")

# --- Existing time routing unchanged ---
print("\n--- Time routing (unchanged) ---")
check("What time is it?", ACTION_TIME, "time question routes time")
check("What is today's date?", ACTION_TIME, "date question routes time")

# --- Existing chat routing unchanged ---
print("\n--- Chat routing (unchanged) ---")
check("hi", ACTION_CHAT, "greeting stays chat")
check("hello", ACTION_CHAT, "hello stays chat")
check("How are you?", ACTION_CHAT, "how are you stays chat")
check("Tell me a joke", ACTION_CREATIVE, "joke routes creative")

# --- Summary ---
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
if FAIL == 0:
    print("ALL PLANNER TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)