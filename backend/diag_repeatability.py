"""Repeatability experiment: 4 questions x 10 runs each."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import ask_llm, OLLAMA_MODEL, _generation_options

agent = Agent()

questions = [
    ("If I have 5 apples and give away 2, how many remain?", "3"),
    ("What comes next: 2, 4, 8, 16, ?", "32"),
    ("What is 27 * 43?", "1161"),
    ("The Amazon river flows through Africa. True or false?", "False"),
]

print("=" * 70)
print("REPEATABILITY EXPERIMENT: 4 questions x 10 runs")
print("=" * 70)
print(f"Model: {OLLAMA_MODEL}")
print(f"Temperature: {_generation_options().get('temperature')}")
print()

for q_idx, (question, expected) in enumerate(questions, 1):
    print("=" * 70)
    print(f"QUESTION {q_idx}: {question}")
    print(f"Expected: {expected}")
    print("=" * 70)
    
    answers = []
    for run in range(10):
        start = time.perf_counter()
        result = agent.run(question, chat_id=9999, user_id=8888)
        answer = ask_llm(result["prompt"])
        latency = (time.perf_counter() - start) * 1000
        
        action = result.get("action", "unknown")
        rag_used = result.get("context") is not None
        answers.append(answer.strip())
        
        print(f"  Run {run+1:2d}: {answer.strip()[:120]}")
        print(f"         Latency: {latency:.0f}ms | Action: {action} | RAG: {rag_used}")
    
    # Analysis
    correct = sum(1 for a in answers if expected.lower() in a.lower())
    incorrect = 10 - correct
    unique = len(set(answers))
    consistency = (1 - (unique - 1) / max(len(answers) - 1, 1)) * 100 if len(answers) > 1 else 100
    
    print()
    print(f"  Correct: {correct}/10 | Incorrect: {incorrect}/10")
    print(f"  Unique answers: {unique} | Consistency: {consistency:.0f}%")
    print(f"  Stochastic: {'YES' if unique > 1 else 'NO - deterministic'}")
    print()
    
    for i, a in enumerate(answers, 1):
        print(f"    Run {i}: {a[:100]}")
    print()

print("=" * 70)
print("FINAL CLASSIFICATION")
print("=" * 70)
print("A. consistent model limitations - if all 10 runs give same wrong answer")
print("B. stochastic/variable model behavior - if answers vary across runs")
print("C. routing/tool issue - if action/rag differ")
print("D. something else")