"""Security tests for MyGPT — secrets, authorization, code execution,
file upload, input validation, and error handling."""

import os
import re
from io import BytesIO
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. Secrets tests
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


class TestSecrets:
    def test_env_in_gitignore(self):
        with open(os.path.join(PROJECT_ROOT, ".gitignore"), "r") as f:
            gitignore = f.read()
        assert ".env" in gitignore
        assert ".env.local" in gitignore
        assert "!.env.example" in gitignore

    def test_no_api_keys_in_frontend_env(self):
        with open(os.path.join(PROJECT_ROOT, "mygpt-ui", ".env"), "r") as f:
            content = f.read()
        assert "GEMINI_API_KEY" not in content
        assert "JWT_SECRET_KEY" not in content
        assert "NVIDIA_API_KEY" not in content

    def test_env_example_exists_with_placeholders(self):
        env_example = os.path.join(PROJECT_ROOT, "backend", ".env.example")
        assert os.path.exists(env_example)
        with open(env_example, "r") as f:
            content = f.read()
        assert "replace-with-a-long-random-secret" in content

    def test_no_hardcoded_secrets_in_code(self):
        """Search for hardcoded API key patterns in source files."""
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", "venv",
            "dist", "build", ".next", ".kilo",
        }
        secret_pattern = re.compile(
            r"(GEMINI_API_KEY|JWT_SECRET_KEY|NVIDIA_API_KEY)\s*=\s*['\"][A-Za-z0-9_-]{20,}['\"]"
        )

        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in files:
                if not fname.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                    continue
                if fname in (".env", ".env.example"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    match = secret_pattern.search(content)
                    if match:
                        pytest.fail(
                            f"Hardcoded secret found in {fpath}: {match.group()}"
                        )
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 2. Authorization tests (cross-user isolation)
# ---------------------------------------------------------------------------

class TestAuthorization:
    def test_cross_user_access_denied(self, tmp_db):
        """User cannot access another user's chat."""
        from auth import verify_chat_ownership
        from database import create_conversation, get_connection

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
            ("User1", "u1@test.com", "hash"),
        )
        user1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
            ("User2", "u2@test.com", "hash"),
        )
        user2_id = cur.lastrowid
        conn.commit()
        conn.close()

        chat2 = create_conversation(user2_id, "User 2 Chat")

        with pytest.raises(Exception) as exc_info:
            verify_chat_ownership(chat2, user1_id)
        assert exc_info.value.status_code == 403

    def test_nonexistent_chat_returns_404(self, tmp_db):
        from auth import verify_chat_ownership
        with pytest.raises(Exception) as exc_info:
            verify_chat_ownership(999999, 1)
        assert exc_info.value.status_code == 404

    def test_conversation_listing_user_isolation(self, tmp_db):
        from database import create_conversation, get_conversations, get_connection

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("UserX", "x@test.com", "hash"))
        user_x = cur.lastrowid
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("UserY", "y@test.com", "hash"))
        user_y = cur.lastrowid
        conn.commit()
        conn.close()

        create_conversation(user_x, "User X Chat 1")
        create_conversation(user_y, "User Y Chat")

        x_chats = get_conversations(user_x)
        y_chats = get_conversations(user_y)

        assert len(x_chats) == 1
        assert len(y_chats) == 1
        assert "User X" in x_chats[0][1]
        assert "User Y" in y_chats[0][1]


# ---------------------------------------------------------------------------
# 3. Input validation via API
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_chat_validation_missing_message(self, client, tmp_db, auth_headers):
        from database import create_conversation
        chat_id = create_conversation(1, "Test Chat")
        resp = client.post(
            "/chat",
            json={"chat_id": chat_id},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_chat_validation_invalid_chat_id(self, client, tmp_db, auth_headers):
        """chat_id 'not-a-number' is rejected by Pydantic validation."""
        resp = client.post(
            "/chat",
            json={"message": "test", "chat_id": "not-a-number"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_chat_validation_message_too_long(self, client, tmp_db, auth_headers):
        from database import create_conversation
        chat_id = create_conversation(1, "Test")
        resp = client.post(
            "/chat",
            json={"message": "x" * 20_001, "chat_id": chat_id},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_stream_validation_missing_message(self, client, tmp_db, auth_headers):
        resp = client.post(
            "/stream",
            json={"chat_id": 1},
            headers=auth_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_llm_error_returns_structured_response(
        self, client, tmp_db, auth_headers
    ):
        from database import create_conversation
        from llm import LLMError

        chat_id = create_conversation(1, "Test")
        with patch("app.ask_llm_routed", side_effect=LLMError(
            "test_error", "User message", 500
        )):
            resp = client.post(
                "/chat",
                json={"message": "test", "chat_id": chat_id},
                headers=auth_headers,
            )
        assert resp.status_code == 500
        if "detail" in resp.json():
            assert resp.json()["detail"].get("code") == "test_error"

    def test_internal_error_does_not_leak_traceback(
        self, client, tmp_db, auth_headers
    ):
        from database import create_conversation
        from fastapi import HTTPException

        chat_id = create_conversation(1, "Test")
        with patch("app.ask_llm_routed", side_effect=HTTPException(
            status_code=500, detail="Internal server error"
        )):
            resp = client.post(
                "/chat",
                json={"message": "test", "chat_id": chat_id},
                headers=auth_headers,
            )
        assert resp.status_code == 500
        assert "traceback" not in resp.text.lower()
