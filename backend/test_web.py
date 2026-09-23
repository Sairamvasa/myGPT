"""Focused tests for web_search() improvements."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agents.tools import web_search, _reformulate_query, _filter_and_rank_results

PASS = 0
FAIL = 0

def check(label, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  PASS: {label}")
    else:
        FAIL += 1
        print(f"  FAIL: {label}")
        print(f"        Expected: {expected!r}")
        print(f"        Got:      {actual!r}")

print("=" * 70)
print("WEB SEARCH IMPROVEMENT TESTS")
print("=" * 70)

# --- Query reformulation ---
print("\n--- Query reformulation ---")
q, r, reason = _reformulate_query("What is the capital of France in Asia?")
check("France-in-Asia reformulated", r, True)
check("France-in-Asia final query", q, "capital of France")
check("France-in-Asia reason", reason is not None, True)

q, r, reason = _reformulate_query("What is the capital of France?")
check("Normal capital query unchanged", r, False)
check("Normal capital query final", q, "What is the capital of France?")

q, r, reason = _reformulate_query("Who is the president of Mars?")
check("Mars query reformulated", r, True)
check("Mars query disambiguation", "planet Mars" in q, True)

q, r, reason = _reformulate_query("What is the weather today?")
check("Weather query unchanged", r, False)

q, r, reason = _reformulate_query("What are the latest AI news headlines?")
check("News query unchanged", r, False)

# --- Return contract ---
print("\n--- Return contract ---")
result = web_search("capital of France", max_results=3)
check("Returns dict", isinstance(result, dict), True)
check("Has results key", "results" in result, True)
check("Has original_query key", "original_query" in result, True)
check("Has final_query key", "final_query" in result, True)
check("Has reformulated key", "reformulated" in result, True)
check("Has total_found key", "total_found" in result, True)
check("Has returned key", "returned" in result, True)

# --- Normal query behavior ---
print("\n--- Normal query behavior ---")
result = web_search("capital of France", max_results=3)
check("Normal query returns results", len(result["results"]) > 0, True)
check("Normal query not reformulated", result["reformulated"], False)
check("Normal query final == original", result["final_query"], result["original_query"])

# --- France-in-Asia reformulation ---
print("\n--- France-in-Asia handling ---")
result = web_search("What is the capital of France in Asia?", max_results=3)
check("France-in-Asia reformulated", result["reformulated"], True)
check("France-in-Asia final query != original",
      result["final_query"] != result["original_query"], True)
check("France-in-Asia final query is 'capital of France'",
      result["final_query"], "capital of France")
check("France-in-Asia returns results", len(result["results"]) > 0, True)
check("France-in-Asia has reason", result.get("reformulation_reason") is not None, True)

# --- Mars ambiguity handling ---
print("\n--- Mars ambiguity handling ---")
result = web_search("Who is the president of Mars?", max_results=3)
check("Mars query reformulated", result["reformulated"], True)
check("Mars query contains planet Mars", "planet Mars" in result["final_query"], True)

# --- Search failure safety ---
print("\n--- Search failure safety ---")
result = web_search("", max_results=3)
check("Empty query returns dict", isinstance(result, dict), True)
check("Empty query has results key", "results" in result, True)

# --- Existing weather/news still work ---
print("\n--- Existing queries still work ---")
result = web_search("What is the weather today?", max_results=3)
check("Weather query returns dict", isinstance(result, dict), True)
check("Weather query not reformulated", result["reformulated"], False)

result = web_search("What are the latest AI news headlines?", max_results=3)
check("News query returns dict", isinstance(result, dict), True)
check("News query not reformulated", result["reformulated"], False)

# --- Result filtering ---
print("\n--- Result filtering ---")
# Test that low-quality domains are penalized
low_q = {
    "title": "TikTok video",
    "body": "some random content",
    "link": "https://www.tiktok.com/video/123"
}
high_q = {
    "title": "Capital of France",
    "body": "Paris is the capital of France, located in Europe.",
    "link": "https://en.wikipedia.org/wiki/Paris"
}
scored = _filter_and_rank_results([low_q, high_q], "capital of France")
check("Low-quality result filtered", low_q not in scored, True)
check("High-quality result retained", high_q in scored, True)

# --- Summary ---
print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
if FAIL == 0:
    print("ALL WEB SEARCH TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)