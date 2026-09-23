"""Test conversation-memory fix: send 2 messages, verify context flows."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import ask_llm, OLLAMA_MODEL
from database import get_history, get_all_memories

CHAT_ID = 9002
USER_ID = 8002

print("=" * 70)
print("CONVERSATION-MEMORY FIX TEST")
print("=" * 70)

agent = Agent()

# Step 1
print("\n--- Step 1: 'My favorite language is Python.' ---")
result1 = agent.run("My favorite language is Python.", chat_id=CHAT_ID, user_id=USER_ID)
print(f"Action: {result1['action']}")
print(f"History: {len(result1['history'])} msgs")
print(f"Memories: {result1['memories']}")

db_hist1 = get_history(CHAT_ID)
db_mem1 = get_all_memories(USER_ID)
print(f"DB history: {len(db_hist1)} msgs")
print(f"DB memories: {len(db_mem1)}")
for m in db_mem1:
    print(f"  - {m}")

# Step 2
print("\n--- Step 2: 'What is my favorite language?' ---")
result2 = agent.run("What is my favorite language?", chat_id=CHAT_ID, user_id=USER_ID)
print(f"Action: {result2['action']}")
print(f"History retrieved: {len(result2['history'])} msgs")
print(f"Memories: {result2['memories']}")

for role, msg in result2['history']:
    print(f"  [{role}]: {msg[:100]}")

# Check prompt
prompt = result2['prompt']
print(f"\nPrompt length: {len(prompt)} chars")
print(f"Contains 'Python': {'Python' in prompt}")
print(f"Contains 'favorite language': {'favorite language' in prompt.lower()}")
print(f"Contains 'MyGPT' (system prompt): {'MyGPT' in prompt}")

# Get answer
print("\n--- LLM Answer ---")
answer = ask_llm(result2['prompt'])
print(f"Answer: {answer}")
print(f"Contains 'Python': {'python' in answer.lower()}")

# Summary
print("\n" + "=" * 70)
print("RESULTS")
print("=" * 70)
print(f"Message 1 saved to DB: {len(db_hist1) > 0}")
print(f"Message 2 retrieves history: {len(result2['history']) > 0}")
print(f"Prompt contains history: {'Python' in prompt}")
print(f"Answer contains Python: {'python' in answer.lower()}")
print(f"Memory saved: {len(db_mem1) > 0}")