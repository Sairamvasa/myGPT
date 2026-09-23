"""Focused tests for the Apple subtraction checker in test_evaluation.py."""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(__file__))

# Replicate the exact checker logic from test_evaluation.py
def check_apples(answer, criteria):
    if re.search(r"\b3\b", answer):
        return True, "Correct arithmetic (answer contains 3)"
    return False, "Wrong arithmetic (answer does not contain 3)"

PASS = 0
FAIL = 0

def check(label, answer, expected_pass):
    global PASS, FAIL
    passed, detail = check_apples(answer, None)
    if passed == expected_pass:
        PASS += 1
        print(f"  PASS: {label}")
    else:
        FAIL += 1
        print(f"  FAIL: {label}")
        print(f"        Answer: {answer!r}")
        print(f"        Expected pass={expected_pass}, Got pass={passed} ({detail})")

print("=" * 70)
print("APPLE SUBTRACTION CHECKER TESTS")
print("=" * 70)

print("\n--- Should PASS (answer contains standalone 3) ---")
check("5 - 2 = 3", "5 - 2 = 3", True)
check("3 apples remain", "3 apples remain", True)
check("There are 3 left", "There are 3 left", True)
check("The answer is 3.", "The answer is 3.", True)
check("3", "3", True)

print("\n--- Should FAIL (answer does not contain 3) ---")
check("5", "5", False)
check("2", "2", False)
check("4", "4", False)
check("10", "10", False)
check("I don't know", "I don't know", False)

print("\n--- Edge cases ---")
check("Empty string", "", False)
check("30 should be rejected (not 3)", "The answer is 30.", False)  # \b3\b correctly rejects "30"

print("\n" + "=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
if FAIL == 0:
    print("ALL CHECKER TESTS PASSED")
else:
    print(f"{FAIL} TEST(S) FAILED")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)