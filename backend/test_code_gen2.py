import sys
import io
import os
from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agents.agent import Agent
from llm import ask_llm_routed, OLLAMA_MODEL
from perf_telemetry import create_context

agent = Agent()

# Test A: Java GCD - this should fall back to Ollama
print("=== Test A: Java GCD (fallback to Ollama) ===")
result = agent.run("Write a Java program to calculate GCD of 48 and 18.", chat_id=1, user_id=1)
print("Action:", result.get("action"))
perf = create_context("test", OLLAMA_MODEL)
try:
    # Force Ollama by using chat action
    answer = ask_llm_routed(result["prompt"], "chat", perf_context=perf)
    print("Answer:", answer[:1500])
except Exception as e:
    print("Error:", type(e).__name__, str(e))

# Test B: Java Prime
print("\n=== Test B: Java Prime (fallback to Ollama) ===")
result2 = agent.run("Write a Java program to check whether 17 is prime.", chat_id=1, user_id=1)
print("Action:", result2.get("action"))
perf2 = create_context("test", OLLAMA_MODEL)
try:
    answer2 = ask_llm_routed(result2["prompt"], "chat", perf_context=perf2)
    print("Answer:", answer2[:1500])
except Exception as e:
    print("Error:", type(e).__name__, str(e))

# Test C: Python Sort
print("\n=== Test C: Python Sort (fallback to Ollama) ===")
result3 = agent.run("Write Python code to sort [5,2,8,1].", chat_id=1, user_id=1)
print("Action:", result3.get("action"))
perf3 = create_context("test", OLLAMA_MODEL)
try:
    answer3 = ask_llm_routed(result3["prompt"], "chat", perf_context=perf3)
    print("Answer:", answer3[:1500])
except Exception as e:
    print("Error:", type(e).__name__, str(e))