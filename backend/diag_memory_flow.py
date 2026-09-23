"""Trace conversation-memory flow: send 2 messages, inspect history/context at each step."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import ask_llm, OLLAMA_MODEL
from database import get_history, get_all_memories, save_memory

# Use a real chat_id and user_id
CHAT_ID = 9001
USER_ID = 8001

print("=" * 70)
print("CONVERSATION-MEMORY FLOW DIAGNOSTIC")
print("=" * 70)
print(f"chat_id: {CHAT_ID}")
print(f"user_id: {USER_ID}")
print()

agent = Agent()

# --- STEP 1: Send "My favorite language is Python." ---
print("=" * 70)
print("STEP 1: Send 'My favorite language is Python.'")
print("=" * 70)

msg1 = "My favorite language is Python."
result1 = agent.run(msg1, chat_id=CHAT_ID, user_id=USER_ID)

print(f"Action: {result1.get('action')}")
print(f"Memories extracted: {result1.get('memories')}")
print(f"History length: {len(result1.get('history', []))}")
print(f"Has context: {result1.get('context') is not None}")
print()

# Check DB state after step 1
db_history1 = get_history(CHAT_ID)
print(f"DB history after step 1: {len(db_history1)} messages")
for role, msg in db_history1:
    print(f"  [{role}]: {msg[:100]}")
print()

db_memories1 = get_all_memories(USER_ID)
print(f"DB memories after step 1: {len(db_memories1)}")
for m in db_memories1:
    print(f"  - {m[:100]}")
print()

# --- STEP 2: Send "What is my favorite language?" ---
print("=" * 70)
print("STEP 2: Send 'What is my favorite language?'")
print("=" * 70)

msg2 = "What is my favorite language?"
result2 = agent.run(msg2, chat_id=CHAT_ID, user_id=USER_ID)

print(f"Action: {result2.get('action')}")
print(f"Memories used: {result2.get('memories')}")
print(f"History length: {len(result2.get('history', []))}")
print(f"Has context: {result2.get('context') is not None}")
print()

# Inspect the history that was passed to the agent
history_passed = result2.get('history', [])
print(f"History passed to agent.run() for step 2: {len(history_passed)} messages")
for role, msg in history_passed:
    print(f"  [{role}]: {msg[:150]}")
print()

# Check DB state after step 2
db_history2 = get_history(CHAT_ID)
print(f"DB history after step 2: {len(db_history2)} messages")
for role, msg in db_history2:
    print(f"  [{role}]: {msg[:100]}")
print()

# Check what the actual prompt sent to LLM looks like
print("=" * 70)
print("PROMPT SENT TO LLM FOR STEP 2")
print("=" * 70)
prompt = result2.get('prompt', '')
print(f"Prompt length: {len(prompt)} chars")
print(f"Contains 'Python': {'Python' in prompt}")
print(f"Contains 'favorite language': {'favorite language' in prompt.lower()}")
print()

# Show the prompt sections
sections = prompt.split("\n\n---\n\n")
print(f"Prompt sections: {len(sections)}")
for i, section in enumerate(sections):
    first_line = section.split("\n")[0][:80]
    print(f"  Section {i}: {first_line}... ({len(section)} chars)")
    if "History" in first_line or "Memory" in first_line:
        print(f"    CONTENT: {section[:500]}")
print()

# --- STEP 3: Get the actual LLM answer ---
print("=" * 70)
print("STEP 3: LLM answer for step 2")
print("=" * 70)
try:
    answer = ask_llm(result2["prompt"])
    print(f"Answer: {answer}")
    print(f"Contains 'Python': {'python' in answer.lower()}")
except Exception as e:
    print(f"LLM Error: {e}")
print()

# --- STEP 4: Check if the issue is in the agent code path ---
print("=" * 70)
print("STEP 4: Agent code path analysis")
print("=" * 70)

# Re-run step 2 with explicit history inspection
from database import get_history as gh

raw_history = gh(CHAT_ID)
print(f"Raw DB history: {len(raw_history)} messages")
for i, (role, msg) in enumerate(raw_history):
    print(f"  [{i}] role={role}, msg={msg[:80]}...")

# Check if the agent.run() for "chat" action returns history
print()
print(f"result2['action'] = {result2.get('action')}")
print(f"result2['history'] = {result2.get('history')}")

# The key question: does the agent include history in the prompt for chat action?
print()
print("KEY FINDING:")
if result2.get('action') == 'chat':
    print("  Action is 'chat'")
    print("  For 'chat' action, agent.run() returns:")
    print(f"    history: {result2.get('history')}")
    print(f"    context: {result2.get('context')}")
    print(f"    memories: {result2.get('memories')}")
    print("  The prompt is just the raw message (no history/context)")
    print(f"  Prompt: {result2.get('prompt', '')[:200]}")
elif result2.get('action') == 'rag':
    print("  Action is 'rag'")
    print("  For 'rag' action, history is cleared to []")
    print(f"  history: {result2.get('history')}")
    print(f"  context: {result2.get('context')}")
else:
    print(f"  Action is '{result2.get('action')}'")

print()
print("=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)