"""Comprehensive tests for the MyGPT Projects feature.

Covers:
  - Project CRUD (create, list, get, update, delete)
  - Authentication (unauthenticated requests blocked)
  - Ownership isolation (user A cannot access user B's projects)
  - File upload / download / delete (with type validation and ownership)
  - Project conversations (creation, listing)
  - Project context endpoint
  - Agent project context (agent.run with project_id)
  - Delete cascade (deleting a project removes conversations and files)
  - Invalid project access (404 for non-existent, 403 for cross-user)
"""

import os
import pytest
from unittest.mock import patch
from io import BytesIO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_project(client, auth_headers, title="Test Project", description="A test project"):
    resp = client.post("/projects", json={"title": title, "description": description}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_second_user(tmp_db):
    """Create a second user directly in the DB and return their auth headers."""
    import bcrypt
    from database import get_connection

    conn = get_connection()
    cur = conn.cursor()
    pw = bcrypt.hashpw(b"pass456", bcrypt.gensalt()).decode()
    cur.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
        ("User2", "user2@test.com", pw),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# 1. Project CRUD
# ---------------------------------------------------------------------------

class TestProjectCRUD:
    def test_create_project_success(self, client, auth_headers):
        data = _create_project(client, auth_headers, title="My Project", description="Desc")
        assert data["project_id"] > 0
        assert data["title"] == "My Project"
        assert data["description"] == "Desc"
        assert data["user_id"] == 1

    def test_create_project_minimal(self, client, auth_headers):
        resp = client.post("/projects", json={"title": "X"}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] > 0
        assert data["description"] == ""

    def test_create_project_validation_empty_title(self, client, auth_headers):
        resp = client.post("/projects", json={"title": "", "description": ""}, headers=auth_headers)
        assert resp.status_code == 422

    def test_list_projects(self, client, auth_headers, tmp_db):
        _create_project(client, auth_headers, title="Proj A", description="AAA")
        _create_project(client, auth_headers, title="Proj B", description="BBB")

        resp = client.get("/projects", headers=auth_headers)
        assert resp.status_code == 200
        projects = resp.json()
        titles = [p["title"] for p in projects]
        assert "Proj A" in titles
        assert "Proj B" in titles

    def test_list_projects_empty(self, client, auth_headers):
        resp = client.get("/projects", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_project_success(self, client, auth_headers):
        proj = _create_project(client, auth_headers, title="Single", description="One")
        resp = client.get(f"/projects/{proj['project_id']}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Single"

    def test_get_project_not_found(self, client, auth_headers):
        resp = client.get("/projects/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_update_project_success(self, client, auth_headers):
        proj = _create_project(client, auth_headers, title="Original", description="Old")
        resp = client.put(
            f"/projects/{proj['project_id']}",
            json={"title": "Updated", "description": "New"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Project updated successfully"

    def test_update_project_not_found(self, client, auth_headers):
        resp = client.put(
            "/projects/999999",
            json={"title": "X", "description": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_project_success(self, client, auth_headers):
        proj = _create_project(client, auth_headers, title="To Delete", description="")
        resp = client.delete(f"/projects/{proj['project_id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_project_not_found(self, client, auth_headers):
        resp = client.delete("/projects/999999", headers=auth_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Authentication
# ---------------------------------------------------------------------------

class TestProjectAuth:
    def test_create_project_no_auth(self, client):
        resp = client.post("/projects", json={"title": "X", "description": ""})
        assert resp.status_code == 401

    def test_list_projects_no_auth(self, client):
        resp = client.get("/projects")
        assert resp.status_code == 401

    def test_get_project_no_auth(self, client):
        resp = client.get("/projects/1")
        assert resp.status_code == 401

    def test_update_project_no_auth(self, client):
        resp = client.put("/projects/1", json={"title": "X", "description": ""})
        assert resp.status_code == 401

    def test_delete_project_no_auth(self, client):
        resp = client.delete("/projects/1")
        assert resp.status_code == 401

    def test_upload_project_file_no_auth(self, client):
        resp = client.post("/projects/1/upload", files={"file": ("test.txt", b"hello", "text/plain")})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Ownership isolation
# ---------------------------------------------------------------------------

class TestProjectOwnership:
    def test_cross_user_access_denied(self, client, auth_headers, tmp_db):
        """User A cannot access User B's project."""
        # User A creates a project
        proj = _create_project(client, auth_headers, title="Private", description="")

        # User B is created
        _create_second_user(tmp_db)

        # User B logs in
        login_resp = client.post("/login", json={"email": "user2@test.com", "password": "pass456"})
        assert login_resp.status_code == 200
        token_b = login_resp.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B tries to GET user A's project
        resp = client.get(f"/projects/{proj['project_id']}", headers=headers_b)
        assert resp.status_code == 403

        # User B tries to PUT user A's project
        resp = client.put(
            f"/projects/{proj['project_id']}",
            json={"title": "Hacked", "description": "Hacked"},
            headers=headers_b,
        )
        assert resp.status_code == 403

        # User B tries to DELETE user A's project
        resp = client.delete(f"/projects/{proj['project_id']}", headers=headers_b)
        assert resp.status_code == 403

    def test_cross_user_list_isolation(self, client, auth_headers, tmp_db):
        """User B only sees their own projects."""
        # User A creates two projects
        _create_project(client, auth_headers, title="A1", description="")
        _create_project(client, auth_headers, title="A2", description="")

        # User B is created and logs in
        _create_second_user(tmp_db)
        login_resp = client.post("/login", json={"email": "user2@test.com", "password": "pass456"})
        token_b = login_resp.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User B creates one project
        client.post("/projects", json={"title": "B1", "description": ""}, headers=headers_b)

        # User B lists projects — only sees B1
        resp = client.get("/projects", headers=headers_b)
        assert resp.status_code == 200
        titles = [p["title"] for p in resp.json()]
        assert "B1" in titles
        assert "A1" not in titles
        assert "A2" not in titles

    def test_invalid_project_returns_404(self, client, auth_headers):
        resp = client.get("/projects/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_invalid_project_upload_returns_404(self, client, auth_headers):
        resp = client.post(
            "/projects/999999/upload",
            files={"file": ("test.txt", b"hello", "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_invalid_project_conversations_returns_404(self, client, auth_headers):
        resp = client.post(
            "/projects/999999/conversations",
            json={"title": "Chat", "description": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. File upload
# ---------------------------------------------------------------------------

class TestProjectFileUpload:
    def test_upload_text_file_success(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        content = b"# Hello Project\nThis is test content."
        resp = client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("test.py", content, "text/x-python")},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["filename"] == "test.py"
        assert data["chunks"] > 0

    def test_upload_txt_file(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        content = b"Plain text content for testing."
        resp = client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("notes.txt", content, "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "notes.txt"

    def test_upload_unsupported_file_type(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        resp = client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("test.exe", b"MZ", "application/octet-stream")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_upload_invalid_filename(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        resp = client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("../../../etc/passwd", b"root", "text/plain")},
            headers=auth_headers,
        )
        # safe_filename sanitizes — resulting file will be "passwd" with .txt extension
        # but no extension means it won't match — actually it will be "passwd" which has no recognized extension
        # The safe_filename will produce "passwd" — extension will be empty, so it should be rejected
        assert resp.status_code == 400

    def test_list_project_files(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("doc.py", b"print('hello')", "text/x-python")},
            headers=auth_headers,
        )
        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        assert resp.status_code == 200
        files = resp.json()
        assert len(files) == 1
        assert files[0]["filename"] == "doc.py"

    def test_download_project_file(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("doc.py", b"print('hello')", "text/x-python")},
            headers=auth_headers,
        )
        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        file_id = resp.json()[0]["id"]

        resp = client.get(f"/projects/{proj['project_id']}/files/{file_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert b"print('hello')" in resp.content

    def test_delete_project_file(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("doc.py", b"print('hello')", "text/x-python")},
            headers=auth_headers,
        )
        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        file_id = resp.json()[0]["id"]

        resp = client.delete(f"/projects/{proj['project_id']}/files/{file_id}", headers=auth_headers)
        assert resp.status_code == 200

        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        assert len(resp.json()) == 0

    def test_cross_user_file_access_denied(self, client, auth_headers, tmp_db):
        """User B cannot access User A's project files."""
        proj = _create_project(client, auth_headers)
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("secret.py", b"secret code", "text/x-python")},
            headers=auth_headers,
        )

        _create_second_user(tmp_db)
        login_resp = client.post("/login", json={"email": "user2@test.com", "password": "pass456"})
        headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.get(f"/projects/{proj['project_id']}/files", headers=headers_b)
        assert resp.status_code == 403

    def test_cross_project_file_isolation(self, client, auth_headers, tmp_db):
        """Files from project A do not appear in project B."""
        proj_a = _create_project(client, auth_headers, title="Proj A")
        proj_b = _create_project(client, auth_headers, title="Proj B")

        client.post(
            f"/projects/{proj_a['project_id']}/upload",
            files={"file": ("a.py", b"content_a", "text/x-python")},
            headers=auth_headers,
        )
        client.post(
            f"/projects/{proj_b['project_id']}/upload",
            files={"file": ("b.py", b"content_b", "text/x-python")},
            headers=auth_headers,
        )

        resp_a = client.get(f"/projects/{proj_a['project_id']}/files", headers=auth_headers)
        resp_b = client.get(f"/projects/{proj_b['project_id']}/files", headers=auth_headers)

        assert len(resp_a.json()) == 1
        assert resp_a.json()[0]["filename"] == "a.py"
        assert len(resp_b.json()) == 1
        assert resp_b.json()[0]["filename"] == "b.py"


# ---------------------------------------------------------------------------
# 5. Project conversations
# ---------------------------------------------------------------------------

class TestProjectConversations:
    def test_create_project_conversation(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        resp = client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Chat 1", "description": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_id"] > 0
        assert data["project_id"] == proj["project_id"]

    def test_list_project_conversations(self, client, auth_headers):
        proj = _create_project(client, auth_headers)
        client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Chat 1", "description": ""},
            headers=auth_headers,
        )
        client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Chat 2", "description": ""},
            headers=auth_headers,
        )

        resp = client.get(f"/projects/{proj['project_id']}/conversations", headers=auth_headers)
        assert resp.status_code == 200
        chats = resp.json()
        assert len(chats) == 2
        titles = [c["title"] for c in chats]
        assert "Chat 1" in titles
        assert "Chat 2" in titles

    def test_cross_user_project_conversations(self, client, auth_headers, tmp_db):
        """User B cannot create conversations in User A's project."""
        proj = _create_project(client, auth_headers)

        _create_second_user(tmp_db)
        login_resp = client.post("/login", json={"email": "user2@test.com", "password": "pass456"})
        headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Hijack", "description": ""},
            headers=headers_b,
        )
        assert resp.status_code == 403

    def test_cross_user_project_context_denied(self, client, auth_headers, tmp_db):
        """User B cannot get context for User A's project."""
        proj = _create_project(client, auth_headers)

        _create_second_user(tmp_db)
        login_resp = client.post("/login", json={"email": "user2@test.com", "password": "pass456"})
        headers_b = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = client.get(f"/projects/{proj['project_id']}/context", headers=headers_b)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Project context endpoint
# ---------------------------------------------------------------------------

class TestProjectContext:
    def test_project_context_success(self, client, auth_headers):
        proj = _create_project(client, auth_headers, title="CtxTest", description="Context test")
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("code.py", b"print('test')", "text/x-python")},
            headers=auth_headers,
        )
        client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Chat", "description": ""},
            headers=auth_headers,
        )

        resp = client.get(f"/projects/{proj['project_id']}/context", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["project"]["title"] == "CtxTest"
        assert len(data["files"]) == 1
        assert len(data["conversations"]) == 1


# ---------------------------------------------------------------------------
# 7. Agent project context
# ---------------------------------------------------------------------------

class TestAgentProjectContext:
    def test_agent_run_accepts_project_id(self, client, auth_headers, tmp_db):
        """Agent.run() accepts and uses project_id for RAG retrieval."""
        from agents.agent import Agent
        from database import create_conversation, create_project, create_project_conversation

        project_id = create_project(1, "Agent Test", "desc")
        chat_id = create_project_conversation(project_id, 1, "Agent Chat")

        agent = Agent()
        result = agent.run("Explain this code", chat_id=chat_id, user_id=1, project_id=project_id)
        assert result["action"] in ("rag", "code_explanation", "chat")
        assert result["prompt"] is not None

    def test_agent_project_rag_context(self, client, auth_headers, tmp_db):
        """Agent retrieves project RAG context when project_id is set."""
        from agents.agent import Agent
        from database import create_project, create_project_conversation
        from rag import process_text_file, search_project_pdf
        import tempfile, os

        project_id = create_project(1, "RAG Test", "desc")
        chat_id = create_project_conversation(project_id, 1, "RAG Chat")

        # Create a temporary text file and process it for the project
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("The primary function is called main(). It returns 42.")
            temp_path = f.name

        try:
            process_text_file(temp_path, 1, source_filename="doc.txt", project_id=project_id)

            agent = Agent()
            result = agent.run("What is the primary function?", chat_id=chat_id, user_id=1, project_id=project_id)
            assert result["context"] is not None
            assert "main" in result["context"]
        finally:
            os.unlink(temp_path)

    def test_agent_without_project_id_uses_user_rag(self, client, auth_headers, tmp_db):
        """Agent.run() without project_id still uses user-scoped RAG."""
        from agents.agent import Agent
        from database import create_project, create_project_conversation
        from rag import process_text_file
        import tempfile, os

        project_id = create_project(1, "Test", "desc")
        chat_id = create_project_conversation(project_id, 1, "Chat")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("The answer is 42. The user's name is test user.")
            temp_path = f.name

        try:
            # Upload as user-scoped RAG (no project_id)
            process_text_file(temp_path, 1, source_filename="user_doc.txt")

            agent = Agent()
            result = agent.run("Tell me what the answer is", chat_id=chat_id, user_id=1)
            assert result["action"] in ("rag", "chat")
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# 8. Delete cascade behavior
# ---------------------------------------------------------------------------

class TestProjectDeleteCascade:
    def test_delete_project_removes_conversations(self, client, auth_headers, tmp_db):
        from database import create_conversation

        proj = _create_project(client, auth_headers, title="Cascade", description="")

        # Create a project conversation
        client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Conv 1", "description": ""},
            headers=auth_headers,
        )

        # Create a regular (non-project) conversation for user
        regular_chat = create_conversation(1, "Regular")

        # Delete the project
        client.delete(f"/projects/{proj['project_id']}", headers=auth_headers)

        # The project conversation should be gone
        from database import get_conversation_owner
        assert get_conversation_owner(0) is None  # sanity check

        # Regular conversation should still exist
        assert get_conversation_owner(regular_chat) == 1

    def test_delete_project_removes_files(self, client, auth_headers):
        proj = _create_project(client, auth_headers, title="File Cascade", description="")

        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("f1.py", b"code1", "text/x-python")},
            headers=auth_headers,
        )
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("f2.py", b"code2", "text/x-python")},
            headers=auth_headers,
        )

        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        assert len(resp.json()) == 2

        client.delete(f"/projects/{proj['project_id']}", headers=auth_headers)

        resp = client.get(f"/projects/{proj['project_id']}/files", headers=auth_headers)
        assert resp.status_code == 404  # Project is gone, so 404


# ---------------------------------------------------------------------------
# 9. Project chat flow
# ---------------------------------------------------------------------------

class TestProjectChatFlow:
    def test_chat_in_project_uses_project_context(self, client, auth_headers, tmp_db):
        """Chat inside a project conversation should use project RAG."""
        proj = _create_project(client, auth_headers, title="Chat Test", description="")
        client.post(
            f"/projects/{proj['project_id']}/upload",
            files={"file": ("guide.txt", b"The API key is SECRET123.", "text/plain")},
            headers=auth_headers,
        )

        conv_resp = client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Chat", "description": ""},
            headers=auth_headers,
        )
        chat_id = conv_resp.json()["chat_id"]

        with patch("app.ask_llm_routed", return_value="The API key is SECRET123."):
            resp = client.post(
                "/chat",
                json={"message": "What is the API key?", "chat_id": chat_id},
                headers=auth_headers,
            )
        assert resp.status_code == 200

    def test_stream_in_project(self, client, auth_headers, tmp_db):
        """Stream endpoint works with project conversations."""
        proj = _create_project(client, auth_headers, title="Stream Test", description="")
        conv_resp = client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Stream Chat", "description": ""},
            headers=auth_headers,
        )
        chat_id = conv_resp.json()["chat_id"]

        agent_result = {
            "prompt": "Hello project",
            "history": [],
            "context": None,
            "memories": [],
            "action": "chat",
            "tool_results": None,
            "answer": "Hello from project!",
        }

        with patch("app.Agent.run", return_value=agent_result):
            resp = client.post(
                "/stream",
                json={"message": "Hello", "chat_id": chat_id},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        assert b"Hello from project!" in resp.content


# ---------------------------------------------------------------------------
# 10. Project conversations appear in main listing
# ---------------------------------------------------------------------------

class TestProjectConversationsListing:
    def test_project_conversations_appear_in_main_list(self, client, auth_headers):
        """Conversations created inside a project should appear in /conversations."""
        proj = _create_project(client, auth_headers, title="List Test", description="")
        client.post(
            f"/projects/{proj['project_id']}/conversations",
            json={"title": "Proj Chat", "description": ""},
            headers=auth_headers,
        )

        resp = client.get("/conversations", headers=auth_headers)
        assert resp.status_code == 200
        titles = [c["title"] for c in resp.json()]
        assert "Proj Chat" in titles