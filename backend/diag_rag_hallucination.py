"""Diagnostic: trace exactly what happens for 'What is the output?' with calculator.py."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

# Step 1: Set up calculator.py
CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9201
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name

from rag import process_text_file, search_pdf, vector_stores, uploaded_files_map
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

print("=" * 70)
print("STEP 1: Check RAG state after upload")
print("=" * 70)
print(f"user_id in vector_stores: {user_id in vector_stores}")
print(f"user_id in uploaded_files_map: {user_id in uploaded_files_map}")
if user_id in uploaded_files_map:
    print(f"Uploaded files: {uploaded_files_map[user_id]}")

# Step 2: Call search_pdf directly and inspect results
print("\n" + "=" * 70)
print("STEP 2: search_pdf('What is the output?', user_id)")
print("=" * 70)

# Monkey-patch to capture similarity_search results
import rag
original_search = None

# Directly inspect what search_pdf returns
context = search_pdf("What is the output?", user_id)
print(f"\nsearch_pdf returned: {context is not None}")
if context:
    print(f"Context length: {len(context)} chars")
    print(f"\n--- FULL CONTEXT ---")
    print(context)
    print(f"--- END CONTEXT ---")
else:
    print("search_pdf returned None!")

# Step 3: Check raw similarity_search results with scores
print("\n" + "=" * 70)
print("STEP 3: Raw similarity_search_with_score")
print("=" * 70)
vs = vector_stores.get(user_id)
if vs:
    docs_and_scores = vs.similarity_search_with_score("What is the output?", k=10)
    for i, (doc, score) in enumerate(docs_and_scores):
        print(f"\n  Result {i}: score={score:.4f}")
        print(f"  Source: {doc.metadata.get('source', 'N/A')}")
        print(f"  Page: {doc.metadata.get('page', 'N/A')}")
        print(f"  Content: {doc.page_content[:200]!r}")

# Step 4: Check database for any factorial-related history/memory
print("\n" + "=" * 70)
print("STEP 4: Check chat history and memory")
print("=" * 70)
from database import get_history, get_all_memories

history = get_history(chat_id)
print(f"Chat history for chat_id={chat_id}: {len(history)} messages")
for role, msg in history:
    print(f"  [{role}]: {msg[:200]}")

memories = get_all_memories(user_id)
print(f"\nMemories for user_id={user_id}: {len(memories)} memories")
for m in memories:
    print(f"  - {m[:200]}")

# Check if any history or memory contains "factorial"
all_text = " ".join([m for _, m in history] + memories).lower()
print(f"\nContains 'factorial' in history/memory: {'factorial' in all_text}")

# Step 5: Build the full agent prompt and inspect
print("\n" + "=" * 70)
print("STEP 5: Full agent.run() prompt inspection")
print("=" * 70)
from agents.agent import Agent
agent = Agent()
result = agent.run("What is the output?", chat_id=chat_id, user_id=user_id)

print(f"\nAction: {result['action']}")
print(f"Has context: {result['context'] is not None}")
print(f"Has tool_results: {result['tool_results'] is not None}")
print(f"Has memories: {len(result['memories']) > 0}")
print(f"History length: {len(result['history'])}")

prompt = result['prompt']
print(f"\nFull prompt length: {len(prompt)} chars")

# Check if calculator.py content is in the prompt
calc_present = "def add(a, b)" in prompt and "return a + b" in prompt and "print(x)" in prompt
print(f"\ncalculator.py content present in prompt: {calc_present}")

# Check for factorial in prompt
print(f"'factorial' in prompt: {'factorial' in prompt.lower()}")

# Print the prompt structure
print(f"\n--- PROMPT STRUCTURE ---")
sections = prompt.split("\n\n---\n\n")
for i, section in enumerate(sections):
    first_line = section.split("\n")[0][:80]
    print(f"  Section {i}: {first_line}... ({len(section)} chars)")

# Print the Document Context section specifically
for section in sections:
    if "Document & Knowledge Context" in section:
        print(f"\n--- DOCUMENT CONTEXT SECTION ---")
        print(section[:1000])
        print(f"... (total {len(section)} chars)")
        break

# Print the user question section
for section in sections:
    if "Current User Request" in section:
        print(f"\n--- USER QUESTION SECTION ---")
        print(section)
        break

# Step 6: Check the SYSTEM_PROMPT for any factorial references
print("\n" + "=" * 70)
print("STEP 6: Check SYSTEM_PROMPT for factorial references")
print("=" * 70)
from agents.prompts import SYSTEM_PROMPT
print(f"SYSTEM_PROMPT contains 'factorial': {'factorial' in SYSTEM_PROMPT.lower()}")
print(f"SYSTEM_PROMPT length: {len(SYSTEM_PROMPT)} chars")

# Step 7: Check _generation_options
print("\n" + "=" * 70)
print("STEP 7: Generation options")
print("=" * 70)
from llm import _generation_options, OLLAMA_NUM_PREDICT, OLLAMA_MODEL
opts = _generation_options()
print(f"Model: {OLLAMA_MODEL}")
print(f"num_predict: {opts['num_predict']}")
print(f"temperature: {opts['temperature']}")
print(f"top_p: {opts['top_p']}")
print(f"num_ctx: {opts['num_ctx']}")

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)