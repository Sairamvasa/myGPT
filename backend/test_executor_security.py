"""Test Python executor security (pytest module).

Verifies that ``agents.code_executor`` blocks dangerous constructs at
validation time, executes safe code, and enforces timeout / output / size
limits.  Runs as a normal pytest module so it can be invoked with
``pytest -q test_executor_security.py``.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import pytest

from agents.code_executor import _validate_code, execute_python


# Patterns that the AST validator MUST reject before any execution.
DANGEROUS_CODES = [
    ("import os", "import os"),
    ("import subprocess", "import subprocess"),
    ("open('/etc/passwd').read()", "open read"),
    ('__import__("os")', "__import__ os"),
    ('eval("1+1")', "eval"),
    ('exec("print(1)")', "exec"),
    ('compile("1+1", "", "eval")', "compile"),
    ('subprocess.run(["ls"])', "subprocess.run"),
    ('__import__("os").system("ls")', "__import__ os.system"),
    ('eval("__import__(\\"os\\").system(\\"ls\\")")', "eval with import"),
    ('exec("import os; os.system(\\"ls\\")")', "exec with import"),
]

# Imports that the validator must block (Phase F: sys / io / dangerous names).
BLOCKED_IMPORTS = [
    ("import sys", "sys"),
    ("import io", "io"),
    ("import os", "os"),
    ("import subprocess", "subprocess"),
    ("import socket", "socket"),
    ("import urllib.request", "urllib"),
    ("import requests", "requests"),
    ("import ctypes", "ctypes"),
    ("import pickle", "pickle"),
    ("from os import path", "os.path"),
    ("from sys import exit", "sys.exit"),
    ("from os import remove", "os.remove"),
]


@pytest.mark.parametrize("code,desc", DANGEROUS_CODES)
def test_dangerous_code_blocked(code, desc):
    errors = _validate_code(code)
    assert errors, f"Expected code to be blocked ({desc}) but validation passed: {code!r}"


@pytest.mark.parametrize("code,desc", BLOCKED_IMPORTS)
def test_blocked_import(code, desc):
    errors = _validate_code(code)
    assert errors, f"Expected 'import {desc}' to be blocked, but validation passed: {code!r}"


def test_import_sys_blocked():
    assert _validate_code("import sys")


def test_import_io_blocked():
    assert _validate_code("import io")


def test_safe_arithmetic_executes():
    result = execute_python("print(1 + 2)", timeout_seconds=5)
    assert result["success"], f"Safe arithmetic failed: {result}"
    assert result["stdout"] == "3", f"Expected stdout '3', got {result['stdout']!r}"


def test_safe_print_executes():
    result = execute_python(
        'print("Hello, World!")\nresult = 2 + 2\nprint(f"2 + 2 = {result}")',
        timeout_seconds=5,
    )
    assert result["success"], f"Safe code failed: {result}"
    assert "Hello, World!" in result["stdout"]
    assert "4" in result["stdout"]


def test_timeout_handling():
    result = execute_python("import time\nwhile True:\n    time.sleep(1)", timeout_seconds=1)
    assert result["timed_out"], f"Expected timeout, got: {result}"


def test_malformed_python_handled():
    result = execute_python("def incomplete(", timeout_seconds=5)
    assert not result["success"], f"Malformed code should not succeed: {result}"
    assert "Syntax error" in result["stderr"], f"Expected syntax error: {result['stderr']!r}"


def test_oversized_code_rejected():
    huge_code = "x = 1\n" * 20000  # ~120KB, exceeds MAX_CODE_CHARS (12000)
    result = execute_python(huge_code, timeout_seconds=5)
    assert not result["success"], f"Oversized code should be rejected: {result}"
    assert "exceeds maximum length" in result["stderr"]


def test_output_limit_enforced():
    result = execute_python('print("x" * 100000)', timeout_seconds=5)
    assert len(result["stdout"]) <= 65000, f"stdout too long ({len(result['stdout'])}) — output limit not enforced"


def test_memory_allocation_handled_gracefully():
    # A large allocation must not crash the parent; it is isolated in the
    # sandboxed subprocess and must return a well-formed result.
    result = execute_python('x = "a" * (10**8)', timeout_seconds=10)
    assert isinstance(result, dict)
    assert "success" in result and "stdout" in result and "stderr" in result
    assert result["exit_code"] in (0, -1, 137) or not result["success"], (
        f"Unexpected memory-test exit_code={result['exit_code']}: {result}"
    )


def test_no_duplicate_validate_python_definition():
    # Phase F: agents/tools.py must define _validate_python exactly once.
    import inspect
    import agents.tools as tools
    src = inspect.getsource(tools)
    assert src.count("def _validate_python") == 1, "Duplicate _validate_python definition found in agents/tools.py"
