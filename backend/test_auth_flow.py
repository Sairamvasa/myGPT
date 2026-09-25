"""Authentication contract tests for login and protected conversation routes."""

import os
import sys
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from jose import jwt

sys.path.insert(0, os.path.dirname(__file__))

import app as app_module
import auth
from database import get_connection


def _token(user_id: int, *, expires: datetime | None = None) -> str:
    payload = {"user_id": user_id, "exp": expires or datetime.utcnow() + timedelta(days=1)}
    return jwt.encode(payload, auth.JWT_SECRET_KEY, algorithm=auth.JWT_ALGORITHM)


def test_login_and_protected_conversation_flow():
    email = f"auth-{uuid4().hex}@example.test"
    client = TestClient(app_module.app)
    try:
        registered = client.post(
            "/register",
            json={"name": "Auth Test", "email": email, "password": "password-123"},
        )
        assert registered.status_code == 200, registered.text

        logged_in = client.post(
            "/login",
            json={"email": email, "password": "password-123"},
        )
        assert logged_in.status_code == 200, logged_in.text
        data = logged_in.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]

        token = data["access_token"]
        conversations = client.get(
            "/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert conversations.status_code == 200, conversations.text

        new_chat = client.post(
            "/new-chat",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert new_chat.status_code == 200, new_chat.text
        assert new_chat.json()["user_id"] == data["user_id"]
    finally:
        conn = get_connection()
        conn.execute("DELETE FROM users WHERE email = ?", (email,))
        conn.commit()
        conn.close()


def test_missing_invalid_and_expired_tokens_are_rejected():
    client = TestClient(app_module.app)

    assert client.get("/conversations").status_code == 401
    assert client.get(
        "/conversations",
        headers={"Authorization": "Bearer not-a-jwt"},
    ).status_code == 401
    assert client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {_token(1, expires=datetime.utcnow() - timedelta(minutes=1))}"},
    ).status_code == 401


def test_valid_token_is_accepted_and_user_isolation_is_enforced():
    client = TestClient(app_module.app)
    user_a = 910001
    user_b = 910002

    app_module.app.dependency_overrides[app_module.get_current_user] = lambda: user_a
    try:
        response = client.get("/conversations")
        assert response.status_code == 200

        with patch("auth.get_conversation_owner", return_value=user_b):
            try:
                auth.verify_chat_ownership(1, user_a)
            except app_module.HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("cross-user conversation access was not rejected")
    finally:
        app_module.app.dependency_overrides.clear()
