import os, sys, time, tempfile, shutil, subprocess
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def get_cpu_mem():
    try:
        r = subprocess.run(["wmic", "cpu", "get", "loadpercentage", "/value"],
                          capture_output=True, text=True, timeout=3)
        cpu = 0
        for line in r.stdout.split("\n"):
            if "LoadPercentage" in line:
                try:
                    cpu = int(line.split("=")[1].strip())
                except:
                    pass
    except:
        cpu = -1
    try:
        r = subprocess.run(["wmic", "OS", "get", "TotalPhysicalMemory,FreePhysicalMemory", "/value"],
                          capture_output=True, text=True, timeout=3)
        total = 0
        free = 0
        for line in r.stdout.split("\n"):
            if "TotalPhysicalMemory" in line:
                try:
                    total = int(line.split("=")[1].strip()) // (1024 * 1024)
                except:
                    pass
            if "FreePhysicalMemory" in line:
                try:
                    free = int(line.split("=")[1].strip()) // (1024 * 1024)
                except:
                    pass
    except:
        total = -1
        free = -1
    return cpu, total, free

def get_ollama_cpu_mem():
    try:
        r = subprocess.run(["wmic", "process", "where", "name='ollama.exe'",
                            "get", "WorkingSetSize,PercentProcessorTime", "/value"],
                          capture_output=True, text=True, timeout=3)
        cpu = 0
        mem = 0
        for line in r.stdout.split("\n"):
            if "PercentProcessorTime" in line:
                try:
                    cpu = int(line.split("=")[1].strip())
                except:
                    pass
            if "WorkingSetSize" in line:
                try:
                    mem = int(line.split("=")[1].strip()) // (1024 * 1024)
                except:
                    pass
        return cpu, mem
    except:
        return -1, -1

def run_benchmark(name, message, user_id=None, chat_id=None, runs=3):
    print("\n" + "=" * 70)
    print("BENCHMARK: " + name + " runs=" + str(runs))
    print("=" * 70)
    agent = Agent()
    result = agent.run(message, chat_id=chat_id, user_id=user_id)
    prompt = result["prompt"]
    for run in range(runs):
        cpu_before, ram_total, ram_free = get_cpu_mem()
        ocpu_before, omem_before = get_ollama_cpu_mem()
        t0 = time.perf_counter()
        t_first = None
        total_text = ""
        timing = {}
        for resp in client.chat(
            model=OLLAMA_MODEL,
            messages=_chat_messages(prompt),
            stream=True,
            options={**_generation_options(), "num_predict": 160},
            keep_alive="10m",
        ):
            if t_first is None:
                t_first = (time.perf_counter() - t0) * 1000
            content = resp.get("message", {}).get("content", "")
            if content:
                total_text += content
            if resp.get("done"):
                timing["total_duration"] = resp.get("total_duration", 0) / 1e9
                timing["load_duration"] = resp.get("load_duration", 0) / 1e9
                timing["prompt_eval_count"] = resp.get("prompt_eval_count", 0)
                timing["eval_count"] = resp.get("eval_count", 0)
                timing["prompt_eval_duration"] = resp.get("prompt_eval_duration", 0) / 1e9
                timing["eval_duration"] = resp.get("eval_duration", 0) / 1e9
        total = (time.perf_counter() - t0) * 1000
        cpu_after, _, ram_free_after = get_cpu_mem()
        ocpu_after, omem_after = get_ollama_cpu_mem()
        tokens = len(total_text.split())
        tok_per_sec = tokens / timing["eval_duration"] if timing.get("eval_duration") else 0
        print("  Run " + str(run + 1) + ":")
        print("    CPU before=" + str(cpu_before) + "% after=" + str(cpu_after) + "%")
        print("    RAM total=" + str(ram_total) + "GB free_before=" + str(ram_free) +
              "GB free_after=" + str(ram_free_after) + "GB")
        print("    Ollama mem=" + str(omem_before) + "MB -> " + str(omem_after) + "MB")
        print("    load_duration=" + str(round(timing["load_duration"], 3)) + "s")
        print("    prompt_eval_count=" + str(timing["prompt_eval_count"]))
        print("    prompt_eval_duration=" + str(round(timing.get("prompt_eval_duration", 0) * 1000)) + "ms")
        print("    eval_count=" + str(timing["eval_count"]))
        print("    eval_duration=" + str(round(timing.get("eval_duration", 0) * 1000)) + "ms")
        print("    TTFT=" + str(round(t_first)) + "ms Total=" + str(round(total)) + "ms")
        print("    Tokens=" + str(tokens) + " tok/s=" + str(round(tok_per_sec, 1)))
        print("    Response=" + repr(total_text[:100]))

run_benchmark("Normal: What is Python?", "What is Python?", runs=3)

user_id = 9991
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

run_benchmark("RAG: Explain this code", "Explain this code",
              user_id=user_id, chat_id=chat_id, runs=3)

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)