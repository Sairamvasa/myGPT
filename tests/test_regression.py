import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_options_login_production_origin(client):
    headers = {
        "Origin": "https://my-gpt-hazel-six.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://my-gpt-hazel-six.vercel.app"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_options_login_current_preview_origin(client):
    headers = {
        "Origin": "https://my-gpt-1q12-e38n35b1z-sairamvasas-projects.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/login", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://my-gpt-1q12-e38n35b1z-sairamvasas-projects.vercel.app"
    )
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_options_stream_vercel_preview_origin(client):
    headers = {
        "Origin": "https://my-gpt-1q12-e38n35b1z-sairamvasas-projects.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization, content-type",
    }
    response = client.options("/stream", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://my-gpt-1q12-e38n35b1z-sairamvasas-projects.vercel.app"
    )
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers or allow_headers == "*"
    assert "content-type" in allow_headers or allow_headers == "*"


def test_options_arbitrary_vercel_preview_regex(client):
    headers = {
        "Origin": "https://my-gpt-feature-abc1234.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/login", headers=headers)
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://my-gpt-feature-abc1234.vercel.app"
    )


def test_unauthenticated_post_stream_remains_protected(client):
    response = client.post(
        "/stream",
        json={"chat_id": 1, "message": "hello"},
    )
    assert response.status_code == 401


def test_login_behavior_invalid_credentials(client):
    response = client.post(
        "/login",
        json={"email": "nonexistent_user_test@example.com", "password": "wrongpassword123"},
    )
    assert response.status_code == 401
    detail = response.json().get("detail")
    assert detail == "Invalid email or password."
