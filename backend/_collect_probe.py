import subprocess, sys, glob, os, time
os.chdir(r"C:\Users\Administrator\Desktop\voice_agent\myGPT\backend")
files = sorted(glob.glob("test_*.py"))
total_start = time.time()
for f in files:
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", f],
            capture_output=True, text=True, timeout=30
        )
        dt = time.time() - t0
        last = (r.stdout + r.stderr).strip().splitlines()
        last = [l for l in last if l.strip()]
        lastline = last[-1] if last else "(no output)"
        status = "OK" if r.returncode == 0 else f"RC{r.returncode}"
        flag = "  <<< ERROR" if r.returncode not in (0,5) else ""
        print(f"{f:45s} {dt:6.2f}s {status:8s} {lastline[:70]}{flag}", flush=True)
    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        print(f"{f:45s} {dt:6.2f}s HANG-TIMEOUT", flush=True)
print(f"\nTotal: {time.time()-total_start:.1f}s")
