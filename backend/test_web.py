"""Focused tests for web_search() improvements."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agents.tools import web_search, _reformulate_query, _filter_and_rank_results


def check(label, actual, expected):
    if actual == expected:
        print(f"  PASS: {label}")
        return True
    else:
        print(f"  FAIL: {label}")
        print(f"        Expected: {expected!r}")
        print(f"        Got:      {actual!r}")
        return False


def run_tests():
    PASS = 0
    FAIL = 0

    print("=" * 70)
    print("WEB SEARCH IMPROVEMENT TESTS")
    print("=" * 70)

    # --- Query reformulation ---
    print("\n--- Query reformulation ---")
    q, r, reason = _reformulate_query("What is the capital of France in Asia?")
    if check("France-in-Asia reformulated", r, True):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia final query", q, "capital of France"):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia reason", reason is not None, True):
        PASS += 1
    else:
        FAIL += 1

    q, r, reason = _reformulate_query("What is the capital of France?")
    if check("Normal capital query unchanged", r, False):
        PASS += 1
    else:
        FAIL += 1
    if check("Normal capital query final", q, "What is the capital of France?"):
        PASS += 1
    else:
        FAIL += 1

    q, r, reason = _reformulate_query("Who is the president of Mars?")
    if check("Mars query reformulated", r, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Mars query disambiguation", "planet Mars" in q, True):
        PASS += 1
    else:
        FAIL += 1

    q, r, reason = _reformulate_query("What is the weather today?")
    if check("Weather query unchanged", r, False):
        PASS += 1
    else:
        FAIL += 1

    q, r, reason = _reformulate_query("What are the latest AI news headlines?")
    if check("News query unchanged", r, False):
        PASS += 1
    else:
        FAIL += 1

    # --- Return contract ---
    print("\n--- Return contract ---")
    result = web_search("capital of France", max_results=3)
    if check("Returns dict", isinstance(result, dict), True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has results key", "results" in result, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has original_query key", "original_query" in result, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has final_query key", "final_query" in result, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has reformulated key", "reformulated" in result, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has total_found key", "total_found" in result, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Has returned key", "returned" in result, True):
        PASS += 1
    else:
        FAIL += 1

    # --- Normal query behavior ---
    print("\n--- Normal query behavior ---")
    result = web_search("capital of France", max_results=3)
    if check("Normal query returns results", len(result["results"]) > 0, True):
        PASS += 1
    else:
        FAIL += 1
    if check("Normal query not reformulated", result["reformulated"], False):
        PASS += 1
    else:
        FAIL += 1
    if check("Normal query final == original", result["final_query"], result["original_query"]):
        PASS += 1
    else:
        FAIL += 1

    # --- France-in-Asia reformulation ---
    print("\n--- France-in-Asia handling ---")
    result = web_search("What is the capital of France in Asia?", max_results=3)
    if check("France-in-Asia reformulated", result["reformulated"], True):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia final query != original",
             result["final_query"] != result["original_query"], True):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia final query is 'capital of France'",
             result["final_query"], "capital of France"):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia returns results", len(result["results"]) > 0, True):
        PASS += 1
    else:
        FAIL += 1
    if check("France-in-Asia has reason", result.get("reformulation_reason") is not None, True):
        PASS += 1
    else:
        FAIL += 1

    # --- Mars ambiguity handling ---
    print("\n--- Mars ambiguity handling ---")
    result = web_search("Who is the president of Mars?", max_results=3)
    if check("Mars query reformulated", result["reformulated"], True):
        PASS += 1
    else:
        FAIL += 1
    if check("Mars query contains planet Mars", "planet Mars" in result["final_query"], True):
        PASS += 1
    else:
        FAIL += 1

    # --- Search failure safety ---
    print("\n--- Search failure safety ---")
    result = web_search("", max_results=3)
    if check("Empty query returns dict", isinstance(result, dict), True):
        PASS += 1
    else:
        FAIL += 1
    if check("Empty query has results key", "results" in result, True):
        PASS += 1
    else:
        FAIL += 1

    # --- Existing weather/news still work ---
    print("\n--- Existing queries still work ---")
    result = web_search("What is the weather today?", max_results=3)
    if check("Weather query returns dict", isinstance(result, dict), True):
        PASS += 1
    else:
        FAIL += 1
    if check("Weather query not reformulated", result["reformulated"], False):
        PASS += 1
    else:
        FAIL += 1

    result = web_search("What are the latest AI news headlines?", max_results=3)
    if check("News query returns dict", isinstance(result, dict), True):
        PASS += 1
    else:
        FAIL += 1
    if check("News query not reformulated", result["reformulated"], False):
        PASS += 1
    else:
        FAIL += 1

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
    if check("Low-quality result filtered", low_q not in scored, True):
        PASS += 1
    else:
        FAIL += 1
    if check("High-quality result retained", high_q in scored, True):
        PASS += 1
    else:
        FAIL += 1

    # --- Summary ---
    print("\n" + "=" * 70)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    if FAIL == 0:
        print("ALL WEB SEARCH TESTS PASSED")
    else:
        print(f"{FAIL} TEST(S) FAILED")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())