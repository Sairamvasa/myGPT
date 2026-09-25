"""Focused tests for the Apple subtraction checker in test_evaluation.py."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

# Replicate the exact checker logic from test_evaluation.py
def check_apples(answer, criteria):
    if re.search(r"\b3\b", answer):
        return True, "Correct arithmetic (answer contains 3)"
    return False, "Wrong arithmetic (answer does not contain 3)"

CASES = [
    pytest.param("5 - 2 = 3", True, id="arithmetic"),
    pytest.param("3 apples remain", True, id="apples"),
    pytest.param("There are 3 left", True, id="left"),
    pytest.param("The answer is 3.", True, id="punctuation"),
    pytest.param("3", True, id="standalone"),
    pytest.param("5", False, id="five"),
    pytest.param("2", False, id="two"),
    pytest.param("4", False, id="four"),
    pytest.param("10", False, id="ten"),
    pytest.param("I don't know", False, id="unknown"),
    pytest.param("", False, id="empty"),
    pytest.param("The answer is 30.", False, id="reject-30"),
]


@pytest.mark.parametrize("answer, expected_pass", CASES)
def test_apple_checker(answer, expected_pass):
    passed, _detail = check_apples(answer, None)
    assert passed is expected_pass


def _run_cli() -> int:
    print("=" * 70)
    print("APPLE SUBTRACTION CHECKER TESTS")
    print("=" * 70)

    failures = 0
    for case in CASES:
        answer = case.values[0]
        expected_pass = case.values[1]
        passed, detail = check_apples(answer, None)
        label = case.id
        if passed == expected_pass:
            print(f"  PASS: {label}")
        else:
            failures += 1
            print(f"  FAIL: {label}")
            print(f"        Answer: {answer!r}")
            print(f"        Expected pass={expected_pass}, Got pass={passed} ({detail})")

    print("\n" + "=" * 70)
    print(f"RESULTS: {len(CASES) - failures} passed, {failures} failed, {len(CASES)} total")
    print("ALL CHECKER TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED")
    print("=" * 70)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_run_cli())