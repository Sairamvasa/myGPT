"""
Rewrite agents/tools.py: Bug 2 (remove duplicate _validate_python)
and Bug 4 (remove sys/io wrapper injection from execute_python).

Run from: backend/
"""
import sys

NEW_SECURITY_BLOCK = r'''
# ---------------------------------------------------------------------------
# Code execution security
# ---------------------------------------------------------------------------

# Modules that must never be importable in user code.
_BLOCKED_IMPORTS: frozenset = frozenset({
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources",
    "signal", "resource", "gc", "weakref",
    "inspect", "dis", "ast", "codeop", "code", "types", "builtins",
    "__main__", "__future__", "__builtin__",
    "pathlib", "shutil", "requests",
})

# Built-in names/identifiers that must not appear in user code.
_BLOCKED_NAMES: frozenset = frozenset({
    "__import__", "breakpoint", "compile", "eval", "exec",
    "getattr", "globals", "input", "locals", "open", "setattr", "vars",
    "exit", "quit", "help", "license", "copyright", "credits",
    # module names that must not be reachable as bare names either
    "sys", "os", "subprocess", "threading", "multiprocessing",
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib",
    "pickle", "marshal", "shelve", "dbm", "sqlite3", "ctypes",
    "mmap", "platform", "sysconfig", "site", "importlib",
    "pkgutil", "runpy", "zipimport", "pkg_resources",
    "pathlib", "shutil", "requests",
})

MAX_CODE_CHARS = 12_000
MAX_OUTPUT_CHARS = 64_000


def _validate_python(code: str) -> List[str]:
    """
    Authoritative Python safety validator (single definition — Bug 2 fix).

    Walks the AST and returns a list of human-readable error strings for
    any blocked import, blocked name usage, dunder-attribute access, or
    blocked built-in call.  Returns an empty list if the code is safe.

    Security rules enforced:
      No imports from _BLOCKED_IMPORTS (filesystem, network, process ...)
      No direct use of names in _BLOCKED_NAMES
      No access to dunder (__xx__) attributes
      No calls to dangerous built-ins (eval, exec, open, __import__ ...)
    """
    errors: List[str] = []

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"Syntax error: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_IMPORTS:
                    errors.append(f"Import of '{alias.name}' is not allowed")

        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _BLOCKED_IMPORTS:
                errors.append(f"Import from '{node.module}' is not allowed")

        elif isinstance(node, ast.Name):
            if node.id in _BLOCKED_NAMES:
                errors.append(f"Use of '{node.id}' is not allowed")

        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                errors.append(
                    f"Access to dunder attribute '{node.attr}' is not allowed"
                )

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in _BLOCKED_NAMES:
                    errors.append(f"Call to '{node.func.id}' is not allowed")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in _BLOCKED_NAMES:
                    errors.append(f"Call to '{node.func.attr}' is not allowed")

    return errors


def _indent_code(code: str, indent: int) -> str:
    """Indent every non-empty line by *indent* spaces."""
    lines = code.splitlines()
    indented = []
    for line in lines:
        if line.strip() == "":
            indented.append("")
        else:
            indented.append(" " * indent + line)
    return "\n".join(indented)


def execute_python(code: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed subprocess with safety controls.

    Security design (Bug 4 fix)
    ---------------------------
    BEFORE this fix the wrapper injected 'import sys' and 'import io' at the
    top of the executed script, making both names available to user code even
    though the AST validator would have rejected 'import sys' in user code.
    subprocess.run(capture_output=True) already captures stdout/stderr at the
    OS level, so the in-process StringIO redirect was both unnecessary AND
    a security hole.

    After this fix:
      1. The wrapper does NOT import sys or io -- those names are absent from
         the executed script's namespace.
      2. stdout/stderr are captured by subprocess.run(capture_output=True).
      3. The wrapper only wraps user code in try/except so tracebacks appear
         in stderr rather than being lost.
      4. Subprocess runs with -I (isolated) mode and a stripped environment
         (no PYTHONPATH, no API keys, no .env values).

    Returns a dict with:
      success   - bool
      stdout    - str
      stderr    - str
      exit_code - int
      timed_out - bool
      error     - str | None
    """
    if len(code) > MAX_CODE_CHARS:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                f"Code rejected: maximum allowed size is {MAX_CODE_CHARS} characters."
            ),
            "exit_code": -1,
            "timed_out": False,
            "error": f"Code exceeds maximum length of {MAX_CODE_CHARS} characters",
        }

    # Validate safety before executing anything.
    safety_errors = _validate_python(code)
    if safety_errors:
        return {
            "success": False,
            "stdout": "",
            "stderr": "\n".join(safety_errors),
            "exit_code": -1,
            "timed_out": False,
            "error": "Safety validation failed: " + "; ".join(safety_errors),
        }

    timeout_seconds = min(max(int(timeout_seconds), 1), 30)

    # SECURITY: do NOT import sys or io here -- that would put them in scope
    # for user code.  subprocess.run(capture_output=True) handles I/O capture
    # at the OS level so no in-process redirect is needed.
    wrapped_code = (
        "try:\n"
        + _indent_code(code, 4)
        + "\nexcept Exception:\n"
        + "    import traceback as _mygpt_tb\n"
        + "    _mygpt_tb.print_exc()\n"
        + "    raise SystemExit(1)\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(wrapped_code)
        temp_file = fh.name

    try:
        # Stripped environment: no PYTHONPATH, no API keys, no secrets.
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

        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = stdout[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = stderr[:MAX_OUTPUT_CHARS] + "\n[stderr truncated]"

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
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "timed_out": False,
            "error": str(exc),
        }
    finally:
        try:
            os.unlink(temp_file)
        except OSError:
            pass

'''


def main():
    path = "agents/tools.py"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Original line count: {len(lines)}")

    # Find first and second _validate_python definitions (0-indexed)
    def_lines = [i for i, l in enumerate(lines) if l.strip().startswith("def _validate_python")]
    print(f"_validate_python at (0-indexed): {def_lines}")

    # We want to:
    # - Keep lines 0..242   (0-indexed, i.e. lines 1-243)
    # - Replace lines 243..515 with new block (lines 244-516 old content)
    # - Keep lines 516..end (line 517 onward = get_current_time)
    
    keep_before = lines[:243]  # lines 1-243 (web search code)
    keep_after  = lines[516:]  # lines 517-525 (get_current_time + eof)

    new_content = "".join(keep_before) + NEW_SECURITY_BLOCK + "".join(keep_after)

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    # Verify
    with open(path, "r", encoding="utf-8") as f:
        new_lines = f.readlines()
    defs = [i+1 for i, l in enumerate(new_lines) if l.strip().startswith("def _validate_python")]
    dups = [i+1 for i, l in enumerate(new_lines) if "import sys" in l and "subprocess" not in l and i > 240]
    print(f"New line count: {len(new_lines)}")
    print(f"_validate_python defs now at lines: {defs}")
    print(f"'import sys' in new security block (should be empty): {dups}")
    print("DONE" if len(defs) == 1 else "ERROR: still has duplicate")


main()
