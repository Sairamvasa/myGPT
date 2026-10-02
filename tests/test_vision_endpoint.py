import pytest
from fastapi.testclient import TestClient
import os
import sys

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from backend.app import app
client = TestClient(app)

def test_vision_no_auth():
    with open("test_image.jpg", "rb") as f:
        response = client.post("/vision", files={"file": f}, data={"prompt": "hello"})
    assert response.status_code == 401

def test_vision_bad_image():
    # Login to get token
    res = client.post("/register", json={"name": "test_vision", "email": "vision@test.com", "password": "password"})
    res = client.post("/login", json={"email": "vision@test.com", "password": "password"})
    token = res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Send empty file
    response = client.post("/vision", headers=headers, files={"file": ("test.jpg", b"", "image/jpeg")}, data={"prompt": "hello"})
    assert response.status_code == 400
    assert "detail" in response.json()
