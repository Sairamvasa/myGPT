"""Comprehensive tests for all FastAPI endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO


# ---------------------------------------------------------------------------
# Health / basic
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_home(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Register / Login
# ---------------------------------------------------------------------------

class TestAuth:
    def test_register_success(self, client):
        resp = client.post("/register", json={
            "name": "New User",
            "email": "newuser@test.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data

    def test_register_duplicate_email(self, client, test_user):
        resp = client.post("/register", json={
            "name": "Dup",
            "email": test_user["email"],
            "password": "password123",
        })
        assert resp.status_code == 409

    def test_register_validation_error(self, client):
        resp = client.post("/register", json={
            "name": "",
            "email": "bad",
            "password": "short",
        })
        assert resp.status_code == 422

    def test_login_success(self, client, test_user):
        resp = client.post("/login", json={
            "email": test_user["email"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data

    def test_login_invalid_password(self, client, test_user):
        resp = client.post("/login", json={
            "email": test_user["email"],
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/login", json={
            "email": "nobody@test.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_me_valid_token(self, client, auth_headers):
        resp = client.get("/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_me_no_token(self, client):
        resp = client.get("/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get("/me", headers={"Authorization": "Bearer invalid"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class TestConversations:
    def test_new_chat(self, client, auth_headers):
        resp = client.post("/new-chat", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "chat_id" in data
        assert data["title"] == "New Chat"

    def test_new_chat_no_auth(self, client):
        resp = client.post("/new-chat")
        assert resp.status_code == 401

    def test_list_conversations(self, client, auth_headers, tmp_db):
        from database import create_conversation
        create_conversation(1, "Chat Alpha")
        create_conversation(1, "Chat Beta")

        resp = client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        chats = resp.json()
        titles = [c["title"] for c in chats]
        assert "Chat Alpha" in titles
        assert "Chat Beta" in titles

    def test_list_conversations_empty(self, client, auth_headers):
        resp = client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_conversations_user_isolation(self, client, auth_headers, tmp_db):
        """Users only see their own conversations."""
        import bcrypt
        from database import create_conversation, get_connection

        conn = get_connection()
        cur = conn.cursor()
        pw = bcrypt.hashpw(b"pass123A", bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("Other", "other@test.com", pw))
        other_id = cur.lastrowid
        conn.commit()
        conn.close()

        create_conversation(other_id, "Other's Chat")
        create_conversation(1, "My Chat")

        # Login as other user
        resp = client.post("/login", json={"email": "other@test.com", "password": "pass123A"})
        token = resp.json()["access_token"]

        resp = client.get("/conversations", headers={"Authorization": f"Bearer {token}"})
        titles = [c["title"] for c in resp.json()]
        assert "Other's Chat" in titles
        assert "My Chat" not in titles

    def test_delete_conversation(self, client, auth_headers, tmp_db):
        from database import create_conversation
        chat_id = create_conversation(1, "To Delete")
        resp = client.delete(f"/conversations/{chat_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "Conversation deleted successfully"

    def test_delete_conversation_no_auth(self, client):
        resp = client.delete("/conversations/1")
        assert resp.status_code == 401

    def test_delete_other_user_conversation(self, client, tmp_db, test_user):
        import bcrypt
        from database import create_conversation, get_connection

        conn = get_connection()
        cur = conn.cursor()
        pw = bcrypt.hashpw(b"pass123B", bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("Other2", "other2@test.com", pw))
        other_id = cur.lastrowid
        conn.commit()
        conn.close()

        chat_id = create_conversation(other_id, "Other's Chat")

        # Login as test_user (user_id=1), not the owner
        resp = client.post("/login", json={"email": "test@example.com", "password": "testpass123"})
        token = resp.json()["access_token"]

        resp = client.delete(
            f"/conversations/{chat_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

class TestChat:
    def _create_chat(self, client, auth_headers, tmp_db):
        from database import create_conversation
        return create_conversation(1, "Chat")

    def test_chat_success(self, client, auth_headers, tmp_db):
        chat_id = self._create_chat(client, auth_headers, tmp_db)
        with patch("app.ask_llm_routed", return_value="AI response"):
            resp = client.post("/chat", json={
                "message": "Hello",
                "chat_id": chat_id,
            }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["answer"] == "AI response"

    def test_chat_no_auth(self, client, tmp_db):
        from database import create_conversation
        chat_id = create_conversation(1, "Test")
        resp = client.post("/chat", json={
            "message": "Hello",
            "chat_id": chat_id,
        })
        assert resp.status_code == 401

    def test_chat_cross_user_forbidden(self, client, tmp_db, test_user):
        import bcrypt
        from database import create_conversation, get_connection

        conn = get_connection()
        cur = conn.cursor()
        pw = bcrypt.hashpw(b"pass123C", bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("Other3", "other3@test.com", pw))
        other_id = cur.lastrowid
        conn.commit()
        conn.close()

        chat_id = create_conversation(other_id, "Other's Chat")

        # Login as user 1
        resp = client.post("/login", json={"email": "test@example.com", "password": "testpass123"})
        token = resp.json()["access_token"]

        resp = client.post("/chat", json={
            "message": "Hello",
            "chat_id": chat_id,
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_chat_direct_answer(self, client, auth_headers, tmp_db):
        """When agent returns a direct answer, LLM is not called."""
        from database import create_conversation
        chat_id = create_conversation(1, "Math")

        agent_result = {
            "prompt": "2+2",
            "history": [],
            "context": None,
            "memories": [],
            "action": "python",
            "tool_results": "Executed Python Code:\n4\n",
            "answer": "4",
        }
        with patch("app.Agent.run", return_value=agent_result):
            resp = client.post("/chat", json={
                "message": "what is 2+2",
                "chat_id": chat_id,
            }, headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["answer"] == "4"

    def test_chat_llm_error(self, client, auth_headers, tmp_db):
        from database import create_conversation
        from llm import LLMError
        chat_id = create_conversation(1, "Error")

        with patch("app.ask_llm_routed", side_effect=LLMError(
            "connection_error", "API unavailable", 503
        )):
            resp = client.post("/chat", json={
                "message": "Hello",
                "chat_id": chat_id,
            }, headers=auth_headers)

        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Streaming endpoint
# ---------------------------------------------------------------------------

class TestStream:
    def test_stream_success(self, client, auth_headers, tmp_db):
        from database import create_conversation
        chat_id = create_conversation(1, "Stream")

        agent_result = {
            "prompt": "Hello",
            "history": [],
            "context": None,
            "memories": [],
            "action": "chat",
            "tool_results": None,
            "answer": None,
        }

        def fake_stream(prompt, action, **kwargs):
            yield "Hello "
            yield "World"

        with patch("app.Agent.run", return_value=agent_result), \
             patch("app.stream_llm_routed", side_effect=fake_stream):
            resp = client.post("/stream", json={
                "message": "Hello",
                "chat_id": chat_id,
            }, headers=auth_headers)

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Hello" in content
        assert "World" in content

    def test_stream_no_auth(self, client):
        resp = client.post("/stream", json={
            "message": "Hello",
            "chat_id": 1,
        })
        assert resp.status_code == 401

    def test_stream_direct_answer(self, client, auth_headers, tmp_db):
        from database import create_conversation
        chat_id = create_conversation(1, "Direct")

        agent_result = {
            "prompt": "test",
            "history": [],
            "context": None,
            "memories": [],
            "action": "action_time",
            "tool_results": "System Clock: 12:00:00",
            "answer": "12:00:00",
        }
        with patch("app.Agent.run", return_value=agent_result):
            resp = client.post("/stream", json={
                "message": "what time is it",
                "chat_id": chat_id,
            }, headers=auth_headers)

        assert resp.status_code == 200
        assert b"12:00:00" in resp.content


# ---------------------------------------------------------------------------
# Vision endpoint
# ---------------------------------------------------------------------------

class TestVision:
    def test_vision_no_auth(self, client):
        resp = client.post("/vision", files={"file": ("test.jpg", b"", "image/jpeg")})
        assert resp.status_code == 401

    def test_vision_bad_image(self, client, auth_headers):
        resp = client.post(
            "/vision",
            files={"file": ("test.jpg", b"", "image/jpeg")},
            data={"prompt": "analyze"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422, 500)

    def test_vision_success(self, client, auth_headers, tmp_db):
        from PIL import Image
        img = Image.new("RGB", (10, 10), color="red")
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        with patch("app.analyze_image", return_value="A red image"):
            resp = client.post(
                "/vision",
                files={"file": ("test.png", buf, "image/png")},
                data={"prompt": "what color is it"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["answer"] == "A red image"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_success(self, client, auth_headers, tmp_db):
        from database import create_conversation, save_message
        chat_id = create_conversation(1, "Hist")
        save_message(chat_id, "user", "Hello")
        save_message(chat_id, "assistant", "Hi there!")

        resp = client.get(f"/history/{chat_id}", headers=auth_headers)
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 2

    def test_history_no_auth(self, client):
        resp = client.get("/history/1")
        assert resp.status_code == 401

    def test_history_cross_user(self, client, tmp_db, test_user):
        import bcrypt
        from database import create_conversation, save_message, get_connection

        conn = get_connection()
        cur = conn.cursor()
        pw = bcrypt.hashpw(b"pass123D", bcrypt.gensalt()).decode()
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     ("Other4", "other4@test.com", pw))
        other_id = cur.lastrowid
        conn.commit()
        conn.close()

        chat_id = create_conversation(other_id, "Other's History")
        save_message(chat_id, "user", "secret")

        resp = client.post("/login", json={"email": "other4@test.com", "password": "pass123D"})
        token = resp.json()["access_token"]

        # User 1 should not access other user's history
        resp = client.post("/login", json={"email": "test@example.com", "password": "testpass123"})
        token1 = resp.json()["access_token"]

        resp = client.get(f"/history/{chat_id}", headers={"Authorization": f"Bearer {token1}"})
        assert resp.status_code == 403

    def test_history_not_found(self, client, auth_headers):
        resp = client.get("/history/999999", headers=auth_headers)
        assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Memories endpoint
# ---------------------------------------------------------------------------

class TestMemoriesEndpoint:
    def test_memories_empty(self, client, auth_headers):
        resp = client.get("/memories", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["memories"] == []

    def test_memories_no_auth(self, client):
        resp = client.get("/memories")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

class TestCORS:
    def test_cors_preflight_vercel(self, client):
        """CORS preflight should succeed for Vercel origins."""
        resp = client.options("/", headers={
            "Origin": "https://mygpt.example.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        })
        assert resp.status_code == 200
        assert "access-control-allow-origin" in {k.lower() for k in resp.headers}

    def test_cors_preflight_localhost(self, client):
        """CORS preflight should succeed for localhost origins."""
        resp = client.options("/", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        })
        assert resp.status_code == 200
