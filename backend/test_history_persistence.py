"""Regression coverage for persisted chat history."""

import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
from database import get_connection


def test_create_chat_send_message_and_read_history():
    user_id = 920001
    client = TestClient(app_module.app)

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: user_id
    try:
        with (
            patch.object(app_module, "verify_chat_ownership"),
            patch.object(
                app_module.agent,
                "run",
                return_value={
                    "prompt": "What is Python?",
                    "history": [],
                    "context": None,
                    "memories": [],
                    "action": "chat",
                    "tool_results": None,
                    "answer": None,
                },
            ),
            patch.object(app_module, "ask_llm_routed", return_value="Python is a programming language."),
        ):
            created = client.post("/new-chat")
            assert created.status_code == 200, created.text
            chat_id = created.json()["chat_id"]

            response = client.post(
                "/chat",
                json={"message": "What is Python?", "chat_id": chat_id},
            )
            assert response.status_code == 200, response.text
            assert response.json()["answer"] == "Python is a programming language."

            history = client.get(f"/history/{chat_id}")
            assert history.status_code == 200, history.text
            assert history.json() == [
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "Python is a programming language."},
            ]
    finally:
        app_module.app.dependency_overrides.clear()
        conn = get_connection()
        conn.execute("DELETE FROM chats WHERE chat_id = ?", (locals().get("chat_id", -1),))
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (locals().get("chat_id", -1), user_id),
        )
        conn.commit()
        conn.close()
