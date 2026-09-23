"""Debug: inspect the actual prompt sent to Ollama for RAG questions."""
import os, sys, time, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from agents.planner import decide
from agents.agent import Agent
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
user_id = 9001
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name

process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

agent = Agent()

for question in ["Explain this code", "What is the output?", "Find any problems in this code"]:
    print(f"\n{'='*60}")
    print(f"QUESTION: {question}")
    print(f"{'='*60}")
    result = agent.run(question, chat_id=1, user_id=user_id)
    print(f"Action: {result['action']}")
    print(f"Has context: {result['context'] is not None}")
    if result['context']:
        print(f"Context length: {len(result['context'])}")
        ctx_safe = result['context'].encode('ascii', errors='replace').decode('ascii')
        print(f"Context preview:\n{ctx_safe[:500]}")
    print(f"\nTool results: {result['tool_results'].encode('ascii', errors='replace').decode('ascii') if result['tool_results'] else 'None'}")
    print(f"\nFull prompt length: {len(result['prompt'])}")
    prompt_safe = result['prompt'].encode('ascii', errors='replace').decode('ascii')
    print(f"\n--- PROMPT (last 2000 chars) ---")
    print(prompt_safe[-2000:])
    print(f"\n--- END PROMPT ---")

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)