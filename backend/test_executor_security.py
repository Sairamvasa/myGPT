"""Test Python executor security."""
import sys
sys.path.insert(0, 'backend')

from agents.code_executor import _validate_code, execute_python

dangerous_codes = [
    ('import os', 'import os'),
    ('import subprocess', 'import subprocess'),
    ('open("/etc/passwd").read()', 'open read'),
    ('__import__("os")', '__import__ os'),
    ('eval("1+1")', 'eval'),
    ('exec("print(1)")', 'exec'),
    ('compile("1+1", "", "eval")', 'compile'),
    ('while True: pass', 'infinite loop'),
    ('subprocess.run(["ls"])', 'subprocess.run'),
    ('__import__("os").system("ls")', '__import__ os.system'),
    ('eval("__import__(\"os\").system(\\"ls\\")")', 'eval with import'),
    ('exec("import os; os.system(\\"ls\\")")', 'exec with import'),
]

print('Testing dangerous code patterns:')
for code, desc in dangerous_codes:
    errors = _validate_code(code)
    blocked = len(errors) > 0
    status = 'BLOCKED' if blocked else 'NOT BLOCKED'
    print(f'  {"BLOCKED" if blocked else "NOT BLOCKED"} {desc}: {len(errors)} errors')
    if errors:
        for e in errors:
            print(f'    - {e}')

# Test execution with safe code
print('\nTesting safe code execution:')
safe_code = 'print("Hello, World!")\nresult = 2 + 2\nprint(f"2 + 2 = {result}")'
result = execute_python(safe_code, timeout_seconds=5)
print(f'  Success: {result["success"]}')
print(f'  Stdout: {result["stdout"]}')
print(f'  Stderr: {result["stderr"]}')
print(f'  Exit code: {result["exit_code"]}')
print(f'  Tokens: {result.get("tokens", "N/A")}')

# Test timeout
print('\nTesting timeout handling:')
timeout_code = 'import time\nwhile True:\n    time.sleep(1)'
result = execute_python(timeout_code, timeout_seconds=1)
print(f'  Timed out: {result["timed_out"]}')
print(f'  Error: {result.get("error")}')

# Test memory limit (should fail gracefully)
print('\nTesting memory limit handling:')
memory_code = 'x = "a" * (10**9)'  # Try to allocate 1GB
result = execute_python(memory_code, timeout_seconds=5)
print(f'  Success: {result["success"]}')
print(f'  Exit code: {result["exit_code"]}')
print(f'  Stderr (truncated): {result["stderr"][:100]}...')