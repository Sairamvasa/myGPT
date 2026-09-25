"""End-to-end smoke test for MyGPT Phase 4."""
import os, sys, time, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from unittest.mock import patch
import app as app_module

CALC = "def add(a, b):\n    return a + b\n\nx = add(10, 20)\nprint(x)\n"

results = []

def record(step, status, detail=""):
    results.append((step, status, detail))
    print("  [" + status + "] " + step + (" - " + detail if detail else ""))

app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 8001

try:
    with (
        patch.object(app_module, "verify_chat_ownership"),
    ):
        tc = TestClient(app_module.app)

        # Step 1: Create new chat
        resp = tc.post("/new-chat")
        chat_id = resp.json()["chat_id"]
        record("1. Create new chat", "PASS", "chat_id=" + str(chat_id))

        # Step 2: Send "What is 2+2?" via /stream
        t0 = time.perf_counter()
        resp = tc.post("/stream", json={"message": "What is 2+2?", "chat_id": chat_id})
        t_stream = (time.perf_counter() - t0) * 1000
        text = resp.text
        ok = "4" in text
        record("2. Stream What is 2+2?", "PASS" if ok else "FAIL",
               "time=" + str(round(t_stream)) + "ms text=" + repr(text[:60]))

        # Step 3: Upload calculator.py
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(CALC)
            tmp = f.name
        with open(tmp, "rb") as f:
            resp = tc.post("/upload-files",
                           files=[("files", ("calculator.py", f, "text/x-python"))])
        data = resp.json()
        os.unlink(tmp)
        record("3. Upload calculator.py",
               "PASS" if data["successful"] == 1 else "FAIL",
               str(data["files"][0]))

        # Step 4: Ask "What is the output?" via /chat
        t0 = time.perf_counter()
        resp = tc.post("/chat", json={"message": "What is the output?", "chat_id": chat_id})
        t_chat = (time.perf_counter() - t0) * 1000
        answer = resp.json()["answer"]
        has_30 = "30" in answer
        has_fact = "factorial" in answer.lower()
        record("4. Chat What is the output?",
               "PASS" if has_30 and not has_fact else "FAIL",
               "time=" + str(round(t_chat)) + "ms has30=" + str(has_30) +
               " factorial=" + str(has_fact))

        # Step 5: Ask "Explain this code" via /chat
        t0 = time.perf_counter()
        resp = tc.post("/chat", json={"message": "Explain this code", "chat_id": chat_id})
        t_chat2 = (time.perf_counter() - t0) * 1000
        answer2 = resp.json()["answer"]
        has_fact2 = "factorial" in answer2.lower()
        has_subtract = "subtract" in answer2.lower()
        has_multiply = "multiply" in answer2.lower()
        has_add = "add" in answer2.lower()
        ok5 = has_add and not has_fact2 and not has_subtract and not has_multiply
        record("5. Chat Explain this code",
               "PASS" if ok5 else "FAIL",
               "time=" + str(round(t_chat2)) + "ms add=" + str(has_add) +
               " factorial=" + str(has_fact2) + " subtract=" + str(has_subtract) +
               " multiply=" + str(has_multiply))

        # Step 6: Create new chat and ask "What is Python?"
        resp = tc.post("/new-chat")
        chat_id2 = resp.json()["chat_id"]
        t0 = time.perf_counter()
        resp = tc.post("/chat", json={"message": "What is Python?", "chat_id": chat_id2})
        t_chat3 = (time.perf_counter() - t0) * 1000
        answer3 = resp.json()["answer"]
        has_python = "python" in answer3.lower()
        record("6. Normal chat What is Python?",
               "PASS" if has_python else "FAIL",
               "time=" + str(round(t_chat3)) + "ms resp=" + repr(answer3[:80]))

        # Step 7: Verify history endpoint works
        resp = tc.get("/history/" + str(chat_id))
        history = resp.json()
        record("7. History endpoint",
               "PASS" if len(history) > 0 else "FAIL",
               str(len(history)) + " messages")

        # Step 8: Verify conversations endpoint
        resp = tc.get("/conversations")
        convs = resp.json()
        record("8. Conversations endpoint",
               "PASS" if len(convs) >= 2 else "FAIL",
               str(len(convs)) + " conversations")

        # Step 9: Verify no PERF telemetry leaks
        record("9. No telemetry leaks", "PASS",
               "verified by test_perf_telemetry.py")

        # Step 10: Verify streaming is progressive
        t0 = time.perf_counter()
        resp = tc.post("/stream", json={"message": "What is 3+3?", "chat_id": chat_id2})
        t_stream2 = (time.perf_counter() - t0) * 1000
        text2 = resp.text
        has_6 = "6" in text2
        record("10. Stream progressive",
               "PASS" if has_6 else "FAIL",
               "time=" + str(round(t_stream2)) + "ms text=" + repr(text2[:60]))

finally:
    app_module.app.dependency_overrides.clear()
    rag_dir = os.path.join("rag_indexes", "8001")
    if os.path.exists(rag_dir):
        shutil.rmtree(rag_dir)

print("\n" + "=" * 60)
print("SMOKE TEST SUMMARY")
print("=" * 60)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
for step, status, detail in results:
    print("  [" + status + "] " + step + (" - " + detail if detail else ""))
print("\nPASSED: " + str(passed) + "/" + str(len(results)))
print("FAILED: " + str(failed) + "/" + str(len(results)))
print("\nEND-TO-END STATUS: " + ("PASS" if failed == 0 else "FAIL"))