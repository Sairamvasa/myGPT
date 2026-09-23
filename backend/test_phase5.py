"""Phase 5 tests: Web reliability, false-premise handling, and query reformulation."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from agents.tools import web_search, _reformulate_query, _score_result
from agents.planner import decide
from agents.agent import Agent

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} - {detail}")

print("=" * 70)
print("PHASE 5 TESTS: Web Reliability + False-Premise Handling")
print("=" * 70)

# ===== TEST 1: Query Reformulation - False Premise =====
print("\n--- Test 1: Query Reformulation - False Premise ---")

# 1a. "What is the capital of France in Asia?" -> "capital of France"
query, reformulated, reason = _reformulate_query("What is the capital of France in Asia?")
check("1a. Capital of France in Asia", reformulated and query == "capital of France", f"got: {query}, reason: {reason}")

# 1b. "What is the capital of Germany in Africa?" -> "capital of Germany"
query, reformulated, reason = _reformulate_query("What is the capital of Germany in Africa?")
check("1b. Capital of Germany in Africa", reformulated and query == "capital of Germany", f"got: {query}, reason: {reason}")

# 1c. "What is the capital of Japan in Europe?" -> "capital of Japan"
query, reformulated, reason = _reformulate_query("What is the capital of Japan in Europe?")
check("1c. Capital of Japan in Europe", reformulated and query == "capital of Japan", f"got: {query}, reason: {reason}")

# 1d. "Which city is the capital of France in Asia?" -> "capital of France"
query, reformulated, reason = _reformulate_query("Which city is the capital of France in Asia?")
check("1d. Which city is capital of France in Asia", reformulated and query == "capital of France", f"got: {query}, reason: {reason}")

# 1e. "Where is the capital of France in Asia?" -> "capital of France"
query, reformulated, reason = _reformulate_query("Where is the capital of France in Asia?")
check("1e. Where is capital of France in Asia", reformulated and query == "capital of France", f"got: {query}, reason: {reason}")

# 1f. Normal query should NOT be reformulated
query, reformulated, reason = _reformulate_query("What is the capital of France?")
check("1f. Normal capital query unchanged", not reformulated and query == "What is the capital of France?", f"got: {query}, reformulated: {reformulated}")

# ===== TEST 2: Planet Ambiguity =====
print("\n--- Test 2: Planet Ambiguity ---")

# 2a. "Who is the president of Mars?" -> "Who is the president of planet Mars?"
query, reformulated, reason = _reformulate_query("Who is the president of Mars?")
check("2a. President of Mars", reformulated and "planet Mars" in query, f"got: {query}, reason: {reason}")

# 2b. "Who is the president of Jupiter?" -> "Who is the president of planet Jupiter?"
query, reformulated, reason = _reformulate_query("Who is the president of Jupiter?")
check("2b. President of Jupiter", reformulated and "planet Jupiter" in query, f"got: {query}, reason: {reason}")

# 2c. "Who is the prime minister of Mars?" -> "Who is the prime minister of planet Mars?"
query, reformulated, reason = _reformulate_query("Who is the prime minister of Mars?")
check("2c. Prime minister of Mars", reformulated and "planet Mars" in query, f"got: {query}, reason: {reason}")

# 2d. "Who is the president of the Moon?" -> "Who is the president of planet Moon?"
query, reformulated, reason = _reformulate_query("Who is the president of the Moon?")
check("2d. President of the Moon", reformulated and "planet Moon" in query, f"got: {query}, reason: {reason}")

# 2e. Mars with company marker should NOT be reformulated
query, reformulated, reason = _reformulate_query("Who is the CEO of Mars Incorporated?")
check("2e. CEO of Mars Incorporated unchanged", not reformulated, f"got: {query}, reformulated: {reformulated}")

# 2e. Normal query about Mars the planet should still work
query, reformulated, reason = _reformulate_query("What is the temperature on Mars?")
check("2f. Temperature on Mars unchanged", not reformulated, f"got: {query}, reformulated: {reformulated}")

# ===== TEST 3: Normal Queries Should Not Be Reformulated =====
print("\n--- Test 3: Normal Queries Unchanged ---")

normal_queries = [
    "weather in Hyderabad today",
    "latest NVIDIA news",
    "current Bitcoin price",
    "Python 3.14 release",
    "weather in Tokyo tomorrow",
    "Apple stock price today",
    "Who won the Super Bowl 2024",
    "Python 3.14 release date",
]

for q in normal_queries:
    query, reformulated, reason = _reformulate_query(q)
    check(f"Normal: {q[:30]}...", not reformulated, f"got: {query}, reformulated: {reformulated}")

# ===== TEST 4: Planner Routing =====
print("\n--- Test 4: Planner Routing ---")

routing_tests = [
    ("What is the capital of France in Asia?", "web"),
    ("What is the capital of Germany in Africa?", "web"),
    ("What is the capital of Japan in Europe?", "web"),
    ("Who is the president of Mars?", "web"),
    ("Who is the president of Jupiter?", "web"),
    ("Who is the prime minister of the Moon?", "web"),
    ("weather in Hyderabad today", "web"),
    ("latest NVIDIA news", "web"),
    ("current Bitcoin price", "web"),
    ("What is Python?", "chat"),
    ("What is 2+2?", "python"),
    ("Explain this code", "rag"),
]

for query, expected in routing_tests:
    action = decide(query)
    check(f"Route: {query[:40]}...", action == expected, f"got: {action}, expected: {expected}")

# ===== TEST 5: Result Scoring - High Authority Domains Boost =====
print("\n--- Test 5: Result Scoring ---")

# High authority domain should get bonus
item_high = {"title": "Capital of France", "body": "Paris is the capital", "href": "https://en.wikipedia.org/wiki/Paris", "domain": "en.wikipedia.org"}
item_low = {"title": "Capital of France", "body": "Paris is the capital", "href": "https://tiktok.com/@user/video", "domain": "tiktok.com"}
item_normal = {"title": "Capital of France", "body": "Paris is the capital", "href": "https://example.com/paris", "domain": "example.com"}

query_terms = ["capital", "france", "paris"]
score_high = _score_result({"title": "Capital of France", "body": "Paris is the capital", "href": "https://en.wikipedia.org/wiki/Paris", "domain": "en.wikipedia.org"}, ["capital", "france", "paris"])
score_low = _score_result({"title": "Capital of France", "body": "Paris is the capital", "href": "https://tiktok.com/@user/video", "domain": "tiktok.com"}, ["capital", "france", "paris"])
score_normal = _score_result({"title": "Capital of France", "body": "Paris is the capital", "href": "https://example.com/paris", "domain": "example.com"}, ["capital", "france", "paris"])

check("High authority domain boosted", score_high > score_normal, f"high={score_high}, normal={score_normal}")
check("Low quality domain penalized", score_normal > score_low, f"normal={score_normal}, low={score_low}")

# ===== TEST 5: Result Filtering - Low Quality Filtered =====
print("\n--- Test 5: Result Filtering ---")

from agents.tools import _filter_and_rank_results

# Create mock results
mock_results = [
    {"title": "Good result", "body": "Good content about Paris", "href": "https://en.wikipedia.org/wiki/Paris", "domain": "en.wikipedia.org"},
    {"title": "TikTok result", "body": "Paris facts", "href": "https://tiktok.com/@user/video", "domain": "tiktok.com"},
    {"title": "Good result 2", "body": "More Paris info", "href": "https://www.britannica.com/place/Paris", "domain": "britannica.com"},
    {"title": "Low quality", "body": "spam content", "href": "https://spam-site.com/paris", "domain": "spam-site.com"},
]

filtered = _filter_and_rank_results(mock_results, "capital of France")
# Should filter out tiktok and spam
domains = [r.get("domain", "") for r in filtered]
check("TikTok filtered out", "tiktok.com" not in domains, f"domains: {domains}")
check("Spam filtered out", "spam-site.com" not in domains, f"domains: {domains}")
check("Wikipedia retained", any("wikipedia" in d for d in domains), f"domains: {domains}")
check("Britannica retained", any("britannica" in d for d in domains), f"domains: {domains}")

# ===== TEST 6: End-to-End Agent Tests =====
print("\n--- Test 6: End-to-End Agent Tests ---")

# We'll test with mocked web search since we can't rely on real DDGS in tests
from unittest.mock import patch, MagicMock

def run_agent_test(question, user_id=9999, chat_id=1):
    """Run agent with mocked web_search"""
    with patch("agents.tools.web_search") as mock_web_search:
        # Mock web_search to return controlled results
        def mock_web_search(query, max_results=5):
            return {
                "results": [
                    {"title": "Capital of France", "body": "Paris is the capital city of France.", "link": "https://en.wikipedia.org/wiki/Paris", "domain": "en.wikipedia.org"},
                    {"title": "France", "body": "France is a country in Europe.", "link": "https://en.wikipedia.org/wiki/France", "domain": "en.wikipedia.org"},
                ],
                "original_query": "capital of France",
                "final_query": "capital of France",
                "reformulated": False,
                "reformulation_reason": None,
                "total_found": 2,
                "returned": 2,
            }
        mock_web_search.side_effect = mock_web_search
        
        agent = Agent()
        result = agent.run("What is the capital of France in Asia?", chat_id=1, user_id=1)
        return result

# Test 1: False premise correction
print("\n--- Test 6a: False Premise Correction (E2E) ---")
result = run_agent_test("What is the capital of France in Asia?")
check("E2E: Capital of France in Asia - action", result["action"] == "web", f"action: {result['action']}")
# Check the final answer (via LLM) would be correct - we check the prompt includes the corrected query
has_corrected_query = "capital of France" in result.get("prompt", "")
check("E2E: Corrected query in prompt", has_corrected_query, f"prompt: {result.get('prompt', '')[:200]}")

# ===== TEST 7: Web Search Metadata Preservation =====
print("\n--- Test 7: Web Search Metadata ---")

result = web_search("What is the capital of France?")
check("7a. Has original_query", "original_query" in result)
check("7b. Has final_query", "final_query" in result)
check("7c. Has reformulated flag", "reformulated" in result)
check("7d. Has reformulation_reason", "reformulation_reason" in result)
check("7e. Has total_found", "total_found" in result)
check("7f. Has returned count", "returned" in result)
check("7g. Results have domain field", all("domain" in r for r in result.get("results", [])), "missing domain in results")

# ===== TEST 8: Web Search Result Structure =====
print("\n--- Test 8: Web Search Result Structure ---")

result = web_search("What is the capital of France?")
results = result.get("results", [])
if results:
    first = results[0]
    check("8a. Result has title", "title" in first)
    check("8b. Result has body", "body" in first)
    check("8c. Result has link", "link" in first)
    check("8d. Result has domain", "domain" in first)

# ===== TEST 9: RAG still works =====
print("\n--- Test 9: RAG Still Works ---")

from rag import process_text_file, search_pdf
import tempfile
import shutil

user_id = 9998
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name

process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

ctx = search_pdf("What is the output?", user_id)
check("RAG: calculator.py retrieved", ctx is not None and "calculator.py" in ctx)
check("RAG: code present", ctx is not None and "add(10, 20)" in ctx)

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# ===== TEST 10: Existing tests still pass =====
print("\n--- Test 10: Existing Tests Pass ---")

# Run a quick check
import subprocess
result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_chat_routing.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_chat_routing.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_agent_context.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_agent_context.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_rag_code.py", "-v", "-x"], capture_output=True, text=True, timeout=120)
check("test_rag_code.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_rag_e2e.py", "-v", "-x"], capture_output=True, text=True, timeout=120)
check("test_rag_e2e.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_rag_history.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_rag_history.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_num_predict.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_num_predict.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_perf_telemetry.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_perf_telemetry.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

result = subprocess.run([sys.executable, "-m", "pytest", "backend/test_rag_threshold.py", "-v", "-x"], capture_output=True, text=True, timeout=60)
check("test_rag_threshold.py passes", result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}")

# ===== SUMMARY =====
print("\n" + "=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 70)

if failed == 0:
    print("ALL TESTS PASSED!")
    sys.exit(0)
else:
    print(f"{failed} TESTS FAILED")
    sys.exit(1)