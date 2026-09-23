"""End-to-end test through FastAPI endpoints: upload calculator.py then ask questions."""

import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
import app as app_module


CALCULATOR_PY = """def add(a, b):
    return a + b

x = add(10, 20)
print(x)
"""


def test_upload_and_chat_with_rag():
    """Upload calculator.py via /upload-files, then ask questions via /chat."""
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 5001
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
        ):
            client = TestClient(app_module.app)

            # 1. Create a chat
            resp = client.post("/new-chat")
            assert resp.status_code == 200
            chat_id = resp.json()["chat_id"]
            print(f"  Created chat_id={chat_id}")

            # 2. Upload calculator.py
            with tempfile.NamedTemporaryFile(
                suffix=".py", delete=False
            ) as f:
                f.write(CALCULATOR_PY.encode("utf-8"))
                tmp_path = f.name

            try:
                with open(tmp_path, "rb") as f:
                    resp = client.post(
                        "/upload-files",
                        files=[("files", ("calculator.py", f, "text/x-python"))],
                    )
                assert resp.status_code == 200, resp.text
                data = resp.json()
                assert data["successful"] == 1, data
                assert data["files"][0]["status"] == "success"
                print(f"  Upload OK: {data['files'][0]}")
            finally:
                os.unlink(tmp_path)

            # 3. Ask questions via /chat (mock Ollama to capture the prompt)
            captured_prompts = []

            def fake_ask(prompt, action, **kwargs):
                captured_prompts.append(prompt)
                return "Mocked Ollama response"

            with patch.object(app_module, "ask_llm_routed", side_effect=fake_ask):
                for question in [
                    "Explain this code",
                    "What is the output?",
                    "Find any problems in this code",
                ]:
                    resp = client.post(
                        "/chat",
                        json={"message": question, "chat_id": chat_id},
                    )
                    assert resp.status_code == 200, resp.text
                    answer = resp.json()["answer"]
                    assert answer == "Mocked Ollama response"
                    # Verify the prompt contains the uploaded file content
                    prompt = captured_prompts[-1]
                    assert "calculator.py" in prompt, (
                        f"Prompt missing calculator.py for: {question}"
                    )
                    assert "def add" in prompt or "add(a, b)" in prompt, (
                        f"Prompt missing add() for: {question}"
                    )
                    print(f"  OK: '{question}' -> prompt contains file content")

            # 4. Normal chat with no file reference stays plain
            with patch.object(app_module, "ask_llm_routed", side_effect=fake_ask):
                resp = client.post(
                    "/chat",
                    json={"message": "Tell me a joke", "chat_id": chat_id},
                )
                assert resp.status_code == 200
                prompt = captured_prompts[-1]
                # Plain chat should NOT include document context
                assert "Document & Knowledge Context" not in prompt or "No documents were uploaded" in prompt, (
                    "Plain chat should not reference uploaded documents"
                )
                print("  OK: normal chat stays plain")

            # 5. Test /stream endpoint
            def fake_stream(prompt, action, **kwargs):
                captured_prompts.append(prompt)
                yield "Streamed response"

            with patch.object(app_module, "stream_llm_routed", side_effect=fake_stream):
                with patch.object(app_module, "is_first_message", return_value=False):
                    resp = client.post(
                        "/stream",
                        json={"message": "Explain this code", "chat_id": chat_id},
                    )
                    assert resp.status_code == 200
                    assert resp.text == "Streamed response"
                    prompt = captured_prompts[-1]
                    assert "calculator.py" in prompt
                    print("  OK: /stream includes file context")

    finally:
        app_module.app.dependency_overrides.clear()
        # Cleanup test user RAG state
        import shutil
        rag_dir = os.path.join("rag_indexes", "5001")
        if os.path.exists(rag_dir):
            shutil.rmtree(rag_dir)


def test_unsupported_file_type():
    """Unsupported file type should be rejected."""
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 5002
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
        ):
            client = TestClient(app_module.app)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
                f.write(b"fake exe content")
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    resp = client.post(
                        "/upload-files",
                        files=[("files", ("test.exe", f, "application/octet-stream"))],
                    )
                assert resp.status_code == 200
                data = resp.json()
                assert data["successful"] == 0
                assert "Unsupported" in data["files"][0]["message"]
                print("  OK: unsupported file type rejected")
            finally:
                os.unlink(tmp_path)
    finally:
        app_module.app.dependency_overrides.clear()


def test_empty_file():
    """Empty file should be rejected."""
    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: 5003
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(app_module, "save_message"),
        ):
            client = TestClient(app_module.app)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
                f.write("")  # empty content
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as f:
                    resp = client.post(
                        "/upload-files",
                        files=[("files", ("empty.py", f, "text/x-python"))],
                    )
                assert resp.status_code == 200
                data = resp.json()
                assert data["successful"] == 0
                print(f"  OK: empty file rejected: {data['files'][0]}")
            finally:
                os.unlink(tmp_path)
    finally:
        app_module.app.dependency_overrides.clear()


if __name__ == "__main__":
    print("=== test_upload_and_chat_with_rag ===")
    test_upload_and_chat_with_rag()
    print("PASS\n")

    print("=== test_unsupported_file_type ===")
    test_unsupported_file_type()
    print("PASS\n")

    print("=== test_empty_file ===")
    test_empty_file()
    print("PASS\n")

    print("ALL E2E TESTS PASSED")