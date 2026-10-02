"""Quick smoke-test for Bug 2 and Bug 4 fixes in agents/tools.py.
Standalone script — run directly with ``python test_bug2_bug4.py``.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from agents.tools import execute_python, _validate_python
import inspect
import agents.tools as t


def main():
    src = inspect.getsource(t)
    count = src.count("def _validate_python")
    print(f"[Bug2] _validate_python definitions: {count} (expected: 1) - {'PASS' if count == 1 else 'FAIL'}")

    errs = _validate_python("x = 1 + 2\nprint(x)")
    print(f"[Bug2] Valid code errors: {errs} (expected: []) - {'PASS' if errs == [] else 'FAIL'}")

    errs = _validate_python("import sys")
    print(f"[Bug2] import sys blocked: {len(errs) > 0} (expected: True) - {'PASS' if errs else 'FAIL'}")
    print(f"         -> {errs}")

    errs = _validate_python("import os\nos.remove('x')")
    print(f"[Bug2] import os blocked: {len(errs) > 0} - {'PASS' if errs else 'FAIL'}")

    # Bug 4: sys must NOT be accessible in subprocess
    res = execute_python("print(1 + 2)")
    print(f"[Bug4] execute print(1+2): success={res['success']} stdout={res['stdout']!r} - {'PASS' if res['success'] and res['stdout'] == '3' else 'FAIL'}")

    res2 = execute_python("x = sys")
    print(f"[Bug4] sys not in scope: success={res2['success']} - {'PASS' if not res2['success'] else 'FAIL'}")
    print(f"         -> stdout={res2['stdout']!r} stderr={res2['stderr'][:80]!r}")

    res3 = execute_python("x = io")
    print(f"[Bug4] io not in scope:  success={res3['success']} - {'PASS' if not res3['success'] else 'FAIL'}")
    print(f"         -> stderr={res3['stderr'][:80]!r}")

    # wrapper injection check: neither sys nor io should appear in wrapper as importable names
    res4 = execute_python("import sys")
    print(f"[Bug4] 'import sys' in exec: blocked by AST: success={res4['success']} - {'PASS' if not res4['success'] else 'FAIL'}")
    print(f"         -> error={res4['error']!r}")

    print("\nAll tests complete.")


if __name__ == "__main__":
    main()
