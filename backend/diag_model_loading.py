"""Diagnose Ollama model loading behavior."""
import os, sys, time, json, urllib.request
sys.path.insert(0, os.path.dirname(__file__))

from llm import OLLAMA_MODEL, OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE, _get_client, _chat_messages, _generation_options

client = _get_client()

# 1. Check /api/ps before any requests
print("=" * 60)
print("1. Ollama /api/ps BEFORE requests")
print("=" * 60)
try:
    req = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=5)
    ps = json.loads(req.read())
    print(json.dumps(ps, indent=2))
except Exception as e:
    print(f"  Error: {e}")

# 2. Check keep_alive config
print(f"\n{'='*60}")
print(f"2. keep_alive configuration")
print(f"{'='*60}")
print(f"  OLLAMA_KEEP_ALIVE = {OLLAMA_KEEP_ALIVE}")
print(f"  OLLAMA_MODEL = {OLLAMA_MODEL}")
print(f"  OLLAMA_BASE_URL = {OLLAMA_BASE_URL}")
print(f"  Client type: {type(client).__name__}")
print(f"  Client is cached: {client is _get_client()}")

# 3. Sequential benchmark
print(f"\n{'='*60}")
print("3. Sequential benchmark (immediate)")
print(f"{'='*60}")

questions_seq = ["What is 2+2?", "What is 3+3?", "What is 4+4?"]

for i, q in enumerate(questions_seq):
    t0 = time.perf_counter()
    t_first = None
    total_text = ""
    done_time = None
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(q),
        stream=True,
        options={**_generation_options(), "num_predict": 160},
        keep_alive=OLLAMA_KEEP_ALIVE,
    ):
        if t_first is None:
            t_first = (time.perf_counter() - t0) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            total_text += content
        if resp.get("done"):
            done_time = (time.perf_counter() - t0) * 1000
            # Check for timing info in done response
            if "total_duration" in resp:
                print(f"  Ollama reported: total_duration={resp['total_duration']/1e9:.2f}s, "
                      f"load_duration={resp.get('load_duration', 'N/A')/1e9:.2f}s, "
                      f"prompt_eval_count={resp.get('prompt_eval_count', 'N/A')}, "
                      f"eval_count={resp.get('eval_count', 'N/A')}")
    total = (time.perf_counter() - t0) * 1000
    tokens = len(total_text.split())
    print(f"  Request {i+1}: '{q}' -> TTFT={t_first:.0f}ms, total={total:.0f}ms, tokens={tokens}")
    print(f"    Response: {total_text[:100]!r}")

# 4. Wait and check /api/ps
print(f"\n{'='*60}")
print("4. Ollama /api/ps AFTER sequential requests")
print("=" * 60)
try:
    req = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=5)
    ps = json.loads(req.read())
    print(json.dumps(ps, indent=2))
except Exception as e:
    print(f"  Error: {e}")

# 5. Wait 5 seconds, then check /api/ps
print(f"\n{'='*60}")
print("5. Waiting 5 seconds, then checking /api/ps")
print(f"{'='*60}")
time.sleep(5)
try:
    req = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=5)
    ps = json.loads(req.read())
    print(json.dumps(ps, indent=2))
except Exception as e:
    print(f"  Error: {e}")

# 6. Single request after wait - check if model was reloaded
print(f"\n{'='*60}")
print("6. Single request after 5s wait")
print(f"{'='*60}")
q = "What is 5+5?"
t0 = time.perf_counter()
t_first = None
total_text = ""
for resp in client.chat(
    model=OLLAMA_MODEL,
    messages=_chat_messages(q),
    stream=True,
    options={**_generation_options(), "num_predict": 160},
    keep_alive=OLLAMA_KEEP_ALIVE,
):
    if t_first is None:
        t_first = (time.perf_counter() - t0) * 1000
    content = resp.get("message", {}).get("content", "")
    if content:
        total_text += content
    if resp.get("done"):
        if "total_duration" in resp:
            print(f"  Ollama reported: total_duration={resp['total_duration']/1e9:.2f}s, "
                  f"load_duration={resp.get('load_duration', 'N/A')/1e9:.2f}s, "
                  f"prompt_eval_count={resp.get('prompt_eval_count', 'N/A')}, "
                  f"eval_count={resp.get('eval_count', 'N/A')}")
        if "prompt_eval_count" in resp:
            print(f"  prompt_eval_count={resp['prompt_eval_count']}, eval_count={resp.get('eval_count', 'N/A')}")
total = (time.perf_counter() - t0) * 1000
tokens = len(total_text.split())
print(f"  TTFT={t_first:.0f}ms, total={total:.0f}ms, tokens={tokens}")
print(f"  Response: {total_text[:100]!r}")

# 7. Check /api/ps after the single request
print(f"\n{'='*60}")
print("7. Ollama /api/ps after single request")
print("=" * 60)
try:
    req = urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/ps", timeout=5)
    ps = json.loads(req.read())
    print(json.dumps(ps, indent=2))
except Exception as e:
    print(f"  Error: {e}")

# 8. Check available memory
print(f"\n{'='*60}")
print("8. System memory")
print(f"{'='*60}")
import subprocess
try:
    result = subprocess.run(["wmic", "OS", "get", "TotalPhysicalMemory,FreePhysicalMemory", "/format:value"], 
                          capture_output=True, text=True, timeout=5)
    print(result.stdout)
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)