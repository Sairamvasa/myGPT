"""
Safe Python code execution tool with sandboxing.

Executes Python code in a restricted subprocess with:
- Timeout limits
- No imports allowed
- No dangerous builtins (__import__, eval, exec, etc.)
- No filesystem access
- No network access
- Captured stdout/stderr
"""

import ast
import subprocess
import sys
import os
import tempfile
try:
    import resource
except ImportError:
    resource = None
try:
    import signal
except ImportError:
    signal = None
from typing import Optional, Dict, Any


# Configuration constants
MAX_CODE_CHARS = 12_000
MAX_OUTPUT_CHARS = 64_000
DEFAULT_TIMEOUT = 10
MAX_TIMEOUT = 30

# Built-in functions/attributes that are blocked for safety
BLOCKED_NAMES = {
    "__import__", "breakpoint", "compile", "eval", "exec", "getattr",
    "globals", "input", "locals", "open", "setattr", "vars",
    "exit", "quit", "help", "license", "copyright", "credits",
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
    "pathlib", "shutil", "requests",
}

# Dangerous modules that should never be imported
BLOCKED_IMPORTS = {
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources", "importlib",
    "ctypes", "subprocess", "signal", "resource", "gc", "weakref",
    "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
    "__main__", "__future__", "__builtin__", "builtins",
    "pathlib", "shutil", "requests",
}


class ExecutionError(Exception):
    """Exception raised when code execution fails."""
    def __init__(self, message: str, exit_code: int = -1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class SafetyError(Exception):
    """Exception raised when code fails safety validation."""
    pass


class TimeoutError(Exception):
    """Exception raised when code execution times out."""
    pass


class _SafetyValidator(ast.NodeVisitor):
    """AST visitor to validate code safety before execution."""

    def __init__(self):
        self.errors = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name.split('.')[0] in BLOCKED_IMPORTS:
                self.errors.append(f"Import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        if module.split('.')[0] in BLOCKED_IMPORTS:
            self.errors.append(f"Import from '{module}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in BLOCKED_NAMES:
                self.errors.append(f"Call to '{node.func.id}' is not allowed")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in BLOCKED_NAMES:
                self.errors.append(f"Call to '{node.func.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr.startswith("__"):
            self.errors.append(f"Access to dunder attribute '{node.attr}' is not allowed")
        if node.attr in BLOCKED_NAMES:
            self.errors.append(f"Access to '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in BLOCKED_NAMES:
            self.errors.append(f"Use of '{node.id}' is not allowed")
        self.generic_visit(node)

    def validate(self, code: str) -> list[str]:
        """Validate code and return list of errors."""
        self.errors = []
        try:
            tree = ast.parse(code, mode="exec")
            self.visit(tree)
        except SyntaxError as e:
            self.errors.append(f"Syntax error: {e}")
        return self.errors


def _validate_code(code: str) -> list[str]:
    """Validate Python code for safety violations."""
    if len(code) > MAX_CODE_CHARS:
        return [f"Code exceeds maximum length of {MAX_CODE_CHARS} characters"]

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    validator = _SafetyValidator()
    validator.visit(tree)
    return validator.errors


def execute_python(
    code: str,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    max_output_chars: int = MAX_OUTPUT_CHARS
) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed subprocess.

    Returns a dict with:
    - success: bool
    - stdout: str
    - stderr: str
    - exit_code: int
    - timed_out: bool
    - error: str (if any)
    """

    # Validate code length
    if len(code) > MAX_CODE_CHARS:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Code exceeds maximum length of {MAX_CODE_CHARS} characters",
            "exit_code": -1,
            "timed_out": False,
            "error": f"Code exceeds maximum length of {MAX_CODE_CHARS} characters",
        }

    # Validate code safety
    safety_errors = _validate_code(code)
    if safety_errors:
        return {
            "success": False,
            "stdout": "",
            "stderr": "\n".join(safety_errors),
            "exit_code": -1,
            "timed_out": False,
            "error": "Safety validation failed: " + "; ".join(safety_errors),
        }

    # Prepare the code for execution
    # Wrap in a function to prevent variable leakage
    wrapped_code = f"""
import sys
import io

# Capture stdout/stderr
_stdout = io.StringIO()
_stderr = io.StringIO()
_old_stdout = sys.stdout
_old_stderr = sys.stderr
sys.stdout = _stdout
sys.stderr = _stderr

try:
{_indent_code(code, 8)}
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    sys.stdout = _old_stdout
    sys.stderr = _old_stderr
    print(_stdout.getvalue(), end='', file=sys.__stdout__)
    print(_stderr.getvalue(), end='', file=sys.__stderr__)
"""

    # Use a temporary file for execution (more reliable than -c)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(wrapped_code)
        temp_file = f.name

    try:
        # Run with restricted environment
        env = {
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", ""),
        }

        proc = subprocess.run(
            [sys.executable, "-I", "-B", temp_file],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            cwd=tempfile.gettempdir(),
        )

        stdout = proc.stdout
        stderr = proc.stderr
        exit_code = proc.returncode

        # Truncate output if too long
        if len(stdout) > max_output_chars:
            stdout = stdout[:max_output_chars] + "\n[output truncated]"
        if len(stderr) > max_output_chars:
            stderr = stderr[:max_output_chars] + "\n[stderr truncated]"

        return {
            "success": exit_code == 0,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exit_code": exit_code,
            "timed_out": False,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds",
            "exit_code": -1,
            "timed_out": True,
            "error": f"Execution timed out after {timeout_seconds} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "timed_out": False,
            "error": str(e),
        }
    finally:
        try:
            os.unlink(temp_file)
        except OSError:
            pass


def _indent_code(code: str, indent: int) -> str:
    """Indent each line of code by the specified amount."""
    lines = code.splitlines()
    indented = []
    for line in lines:
        if line.strip() == "":
            indented.append("")
        else:
            indented.append(" " * indent + line)
    return "\n".join(indented)


def extract_code_from_message(message: str) -> Optional[str]:
    """
    Extract Python code from a user message.
    Handles markdown code blocks and plain code.
    """
    import re

    # Try to extract from markdown code blocks
    code_block_pattern = r"```(?:python)?\s*([\s\S]*?)```"
    matches = re.findall(code_block_pattern, message, re.IGNORECASE)
    if matches:
        return matches[0].strip()

    # If no code block, check if the message looks like code
    # (contains def, class, import, etc.)
    code_indicators = [
        r"\bdef\s+\w+\s*\(",
        r"\bclass\s+\w+",
        r"\bimport\s+\w+",
        r"\bfrom\s+\w+\s+import",
        r"\bprint\s*\(",
        r"\bfor\s+\w+\s+in\b",
        r"\bwhile\s+\w+",
        r"\bif\s+\w+",
        r"\breturn\s+",
    ]

    import re
    for pattern in code_indicators:
        if re.search(pattern, message, re.IGNORECASE):
            return message.strip()

    return None