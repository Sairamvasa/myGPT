"""Helper script to test import of test files with timeout."""
import sys, os, time, subprocess, signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))

files_arg = sys.argv[1:] if len(sys.argv) > 1 else []

if not files_arg:
    # Default: test all files that don't have __main__ guard and aren't already verified
    import glob
    files_arg = []
    verified = {'test_num_predict.py', 'test_phase83_reliability.py', 'test_security.py', 
                'test_evaluation.py', 'test_phase82_security.py',
                'test_word_problem.py', 'test_web.py', 'test_phase5.py', 
                'test_rag_threshold.py', 'test_live_current_info.py',
                'test_provider_routing.py', 'test_code_execution.py', 'test_planner_routing.py'}
    for f in sorted(glob.glob('test_*.py')):
        if f not in verified:
            files_arg.append(f)

for f in files_arg:
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, '-c', f'import importlib.util; spec = importlib.util.spec_from_file_location("{f[:-3]}", "{f}"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)'],
            capture_output=True, text=True, timeout=25,
            cwd=os.getcwd()
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f'{f}: OK ({elapsed:.1f}s)')
        else:
            # Get last line of stderr for the error
            stderr = result.stderr.strip().split('\n')[-1] if result.stderr.strip() else '(no stderr)'
            print(f'{f}: ERROR ({elapsed:.1f}s) - {stderr[:120]}')
    except subprocess.TimeoutExpired:
        print(f'{f}: TIMEOUT (>25s)')
    sys.stdout.flush()
