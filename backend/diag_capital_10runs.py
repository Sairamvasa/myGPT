"""Diagnostic: Run 'What is the capital of Andhra Pradesh?' 10 times."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import ask_llm, OLLAMA_MODEL, _generation_options

agent = Agent()
question = "What is the capital of Andhra Pradesh?"

print("=" * 70)
print("DIAGNOSTIC: 10 runs of 'What is the capital of Andhra Pradesh?'")
print("=" * 70)
print(f"Model: {OLLAMA_MODEL}")
print(f"Temperature: {_generation_options().get('temperature')}")
print()

answers = []
for i in range(10):
    start = time.perf_counter()
    result = agent.run(question, chat_id=9999, user_id=8888)
    answer = ask_llm(result["prompt"])
    latency = (time.perf_counter() - start) * 1000
    
    action = result.get("action", "unknown")
    rag_used = result.get("context") is not None
    
    answers.append(answer.strip())
    
    print(f"Run {i+1:2d}: {answer.strip()[:150]}")
    print(f"       Latency: {latency:.0f}ms | Action: {action} | RAG: {rag_used}")
    print()

# Summary
correct = sum(1 for a in answers if "amaravati" in a.lower())
incorrect = sum(1 for a in answers if "visakhapatnam" in a.lower() or "hyderabad" in a.lower())
other = len(answers) - correct - incorrect
unique = len(set(answers))
consistency = (1 - (unique - 1) / max(len(answers) - 1, 1)) * 100 if len(answers) > 1 else 100

print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Correct (Amaravati):   {correct}/10")
print(f"Incorrect (Visakhapatnam/Hyderabad): {incorrect}/10")
print(f"Other:                 {other}/10")
print(f"Unique answers:        {unique}")
print(f"Consistency:           {consistency:.0f}%")
print(f"Stochastic/variable:   {'YES' if unique > 1 else 'NO - deterministic'}")
print()
for i, a in enumerate(answers, 1):
    print(f"  Run {i}: {a[:120]}")