"""Diagnostic: measure FAISS similarity scores for relevant and unrelated queries."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from rag import vector_stores, uploaded_files_map, _load_user_state
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

user_id = 9951
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

_load_user_state(user_id)
vs = vector_stores.get(user_id)

print("=" * 70)
print("FAISS SCORE DIAGNOSTIC")
print("=" * 70)
print("Vector store type: " + str(type(vs).__name__))

# Check what scoring strategy FAISS uses
if hasattr(vs, "distance_strategy"):
    print("Distance strategy: " + str(vs.distance_strategy))

queries = [
    ("What is the output?", "RELEVANT"),
    ("Explain this code", "RELEVANT"),
    ("What does this code do?", "RELEVANT"),
    ("What is the capital of France?", "UNRELATED"),
    ("How do I bake a cake?", "UNRELATED"),
    ("Tell me about quantum physics", "UNRELATED"),
    ("What is the weather today?", "UNRELATED"),
]

for question, expected in queries:
    print("\n" + "-" * 60)
    print("Query: " + repr(question) + " (" + expected + ")")
    print("-" * 60)
    try:
        docs_and_scores = vs.similarity_search_with_score(question, k=5)
        for i, (doc, score) in enumerate(docs_and_scores):
            source = doc.metadata.get("source", "N/A")
            content_preview = doc.page_content[:80].replace("\n", " ")
            print("  Result " + str(i) + ": score=" + str(round(score, 4)) +
                  " source=" + str(source) + " content=" + repr(content_preview))
    except Exception as e:
        print("  Error: " + str(e))

# Also test with similarity_search (no scores) to confirm it works
print("\n" + "=" * 70)
print("similarity_search (no scores) for comparison")
print("=" * 70)
for question, expected in queries[:3]:
    docs = vs.similarity_search(question, k=3)
    print("  " + repr(question) + ": " + str(len(docs)) + " results")

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)