"""Measure the complete streaming path timing."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import OLLAMA_MODEL, _get_client, _chat_messages, _generation_options
from rag import process_text_file

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"
client = _get_client()

def measure_stream(name, message, user_id=None, chat_id=None):
    print(f"\n{'='*70}")
    print(f"STREAMING PATH: {name} | {message!r}")
    print(f"{'='*70}")

    # Step 1: Frontend click -> backend request
    t_click = time.perf_counter()

    # Step 2: Agent processing (backend start)
    t_agent_start = time.perf_counter()
    agent = Agent()
    result = agent.run(message, chat_id=chat_id, user_id=user_id)
    t_agent_end = time.perf_counter()
    agent_time = (t_agent_end - t_agent_start) * 1000

    prompt = result["prompt"]
    action = result["action"]

    # Step 3: Ollama request start
    t_ollama_start = time.perf_counter()
    t_first = None
    chunks = []
    t_first_chunk = None
    for resp in client.chat(
        model=OLLAMA_MODEL,
        messages=_chat_messages(prompt),
        stream=True,
        options={**_generation_options(), "num_predict": 160},
        keep_alive="10m",
    ):
        if t_first is None:
            t_first = (time.perf_counter() - t_ollama_start) * 1000
        content = resp.get("message", {}).get("content", "")
        if content:
            if t_first_chunk is None:
                t_first_chunk = (time.perf_counter() - t_ollama_start) * 1000
            chunks.append(content)
        if resp.get("done"):
            break
    t_ollama_end = time.perf_counter()
    ollama_total = (t_ollama_end - t_ollama_start) * 1000

    # Step 4: Backend streaming (simulated - FastAPI yields each chunk)
    # In reality, each chunk goes through FastAPI's StreamingResponse
    # We simulate the per-chunk overhead
    t_backend_first = t_first_chunk  # First chunk reaches FastAPI
    t_backend_end = t_ollama_end

    # Step 5: Network transfer to frontend
    # Simulated - each chunk has ~5ms network overhead
    network_overhead_per_chunk = 5  # ms
    t_network_first = t_first_chunk + network_overhead_per_chunk
    t_network_end = ollama_total + (len(chunks) * network_overhead_per_chunk)

    # Step 6: Frontend receives first chunk
    t_frontend_first = t_network_first

    # Step 7: React state update + render
    # React state update is ~16ms (one frame at 60fps)
    react_render_delay = 16
    t_visible = t_frontend_first + react_render_delay

    # Step 8: Final response
    t_final = t_network_end + react_render_delay

    total_text = "".join(chunks)
    out_tokens = len(total_text.split())

    print(f"\n  TIMELINE:")
    print(f"    1. User clicks Send          : 0ms")
    print(f"    2. Backend request starts    : {agent_time:.0f}ms (agent processing)")
    print(f"    3. Ollama request starts     : {agent_time:.0f}ms")
    print(f"    4. Ollama first token (TTFT) : {t_first:.0f}ms")
    print(f"    5. First chunk to FastAPI    : {t_first_chunk:.0f}ms")
    print(f"    6. First chunk to frontend   : {t_network_first:.0f}ms")
    print(f"    7. First visible text        : {t_visible:.0f}ms")
    print(f"    8. Final response            : {t_final:.0f}ms")
    print(f"\n  Chunks: {len(chunks)}")
    print(f"  Output tokens: {out_tokens}")
    print(f"  Response: {total_text[:150]!r}")

    # Check if first visible text is within 1 second
    within_1s = t_visible < 1000
    print(f"\n  First visible text within 1s: {within_1s}")

    return {
        "name": name,
        "agent_time": round(agent_time),
        "ttft": round(t_first),
        "first_chunk": round(t_first_chunk),
        "first_visible": round(t_visible),
        "total": round(t_final),
        "chunks": len(chunks),
        "tokens": out_tokens,
        "within_1s": within_1s,
        "response": total_text,
    }

results = []

# Normal chat
results.append(measure_stream("Normal: What is Python?", "What is Python?"))
results.append(measure_stream("Normal: What is 2+2?", "What is 2+2?"))

# RAG
user_id = 9951
chat_id = 1
rag_dir = os.path.join("rag_indexes", str(user_id))
if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(CALC)
    tmp = f.name
process_text_file(tmp, user_id, source_filename="calculator.py")
os.unlink(tmp)

results.append(measure_stream("RAG: What is the output?", "What is the output?", user_id=user_id, chat_id=chat_id))
results.append(measure_stream("RAG: Explain this code", "Explain this code", user_id=user_id, chat_id=chat_id))
results.append(measure_stream("RAG: What does this code do?", "What does this code do?", user_id=user_id, chat_id=chat_id))

if os.path.exists(rag_dir):
    shutil.rmtree(rag_dir)

# Summary table
print("\n\n" + "=" * 95)
print("STREAMING TIMELINE SUMMARY")
print("=" * 95)
print(f"{'Request':<30} | {'Agent':>7} | {'TTFT':>8} | {'1st Chunk':>10} | {'1st Visible':>12} | {'Total':>8} | {'Chunks':>7} | {'<1s?':>5}")
print("-" * 95)
for r in results:
    print(f"{r['name']:<30} | {r['agent_time']:>6.0f}ms | {r['ttft']:>7.0f}ms | {r['first_chunk']:>9.0f}ms | {r['first_visible']:>11.0f}ms | {r['total']:>7.0f}ms | {r['chunks']:>6} | {str(r['within_1s']):>5}")

with open(os.path.join(os.path.dirname(__file__), "diag_stream.json"), "w") as f:
    json.dump([{k: v for k, v in r.items() if k != 'response'} for r in results], f, indent=2)
print("\nSaved to diag_stream.json")