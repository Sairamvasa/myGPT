"""Tests for RAG relevance threshold."""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(__file__))

from rag import process_text_file, search_pdf, RAG_RELEVANCE_THRESHOLD

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  PASS: " + name + (" - " + detail if detail else ""))
    else:
        failed += 1
        print("  FAIL: " + name + (" - " + detail if detail else ""))

print("=" * 60)
print("TEST: RAG relevance threshold = " + str(RAG_RELEVANCE_THRESHOLD))
print("=" * 60)

# Setup
user_id = 9931
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

# 1. Clearly relevant query -> RAG context returned
print("\n--- Relevant queries ---")
ctx = search_pdf("What is the output?", user_id)
check("relevant: 'What is the output?' returns context", ctx is not None and "calculator.py" in ctx,
      "threshold=" + str(RAG_RELEVANCE_THRESHOLD))

ctx = search_pdf("Explain this code", user_id)
check("relevant: 'Explain this code' returns context", ctx is not None and "calculator.py" in ctx)

ctx = search_pdf("What does this code do?", user_id)
check("relevant: 'What does this code do?' returns context", ctx is not None and "calculator.py" in ctx)

# 2. Clearly unrelated query -> no RAG context
print("\n--- Unrelated queries ---")
ctx = search_pdf("What is the capital of France?", user_id)
check("unrelated: 'capital of France' returns None", ctx is None,
      "score should exceed threshold=" + str(RAG_RELEVANCE_THRESHOLD))

ctx = search_pdf("How do I bake a cake?", user_id)
check("unrelated: 'bake a cake' returns None", ctx is None)

ctx = search_pdf("Tell me about quantum physics", user_id)
check("unrelated: 'quantum physics' returns None", ctx is None)

ctx = search_pdf("What is the weather today?", user_id)
check("unrelated: 'weather today' returns None", ctx is None)

# 3. Boundary/threshold behavior
print("\n--- Boundary behavior ---")
# Test with a very high threshold (should accept everything)
import rag
original = rag.RAG_RELEVANCE_THRESHOLD
try:
    rag.RAG_RELEVANCE_THRESHOLD = 999.0
    ctx = search_pdf("What is the capital of France?", user_id)
    check("boundary: very high threshold accepts unrelated", ctx is not None,
          "threshold=999.0 should accept all")
finally:
    rag.RAG_RELEVANCE_THRESHOLD = original

# Test with a very low threshold (should reject everything)
try:
    rag.RAG_RELEVANCE_THRESHOLD = 0.0
    ctx = search_pdf("What is the output?", user_id)
    check("boundary: very low threshold rejects relevant", ctx is None,
          "threshold=0.0 should reject all")
finally:
    rag.RAG_RELEVANCE_THRESHOLD = original

# 4. Existing empty-file behavior
print("\n--- Empty file behavior ---")
user_id2 = 9932
rag_dir2 = os.path.join("rag_indexes", str(user_id2))
if os.path.exists(rag_dir2):
    shutil.rmtree(rag_dir2)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write("")
    tmp2 = f.name
try:
    process_text_file(tmp2, user_id2, source_filename="empty.py")
except ValueError:
    pass
os.unlink(tmp2)

ctx = search_pdf("What is the output?", user_id2)
check("empty file: returns None", ctx is None)

if os.path.exists(rag_dir2):
    shutil.rmtree(rag_dir2)

# 5. User isolation
print("\n--- User isolation ---")
ctx1 = search_pdf("What is the output?", user_id)
ctx2 = search_pdf("What is the output?", user_id2)
check("user isolation: user 1 has context", ctx1 is not None)
check("user isolation: user 2 has no context", ctx2 is None)

# Cleanup
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n" + "=" * 60)
print("RESULTS: " + str(passed) + " passed, " + str(failed) + " failed")
print("=" * 60)
if failed > 0:
    sys.exit(1)