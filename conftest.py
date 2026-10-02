"""Root conftest — shared fixtures for all tests."""

import os
import sys
import sqlite3
import pytest

# Ensure backend/ is on sys.path for all test files.
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Deterministic JWT secret for test sessions.
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_tests_only")


@pytest.fixture(autouse=True)
def _reset_provider_registry():
    """Clear the global provider registry before and after every test."""
    from providers import registry as _reg_mod

    saved = _reg_mod._registry
    _reg_mod._registry = None

    # Also clear the llm.py cache.
    try:
        import llm as _llm_mod
        _llm_mod._provider_registry = None
    except Exception:
        pass

    yield

    _reg_mod._registry = saved


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear rate-limiter buckets before and after every test."""
    from rate_limiter import rate_limiter
    saved_buckets = dict(rate_limiter._buckets)
    saved_configs = dict(rate_limiter._configs)
    rate_limiter._buckets.clear()
    # Don't clear configs — they are set by the app lifespan.
    yield
    rate_limiter._buckets = saved_buckets
    rate_limiter._configs = saved_configs


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Create a fresh temp SQLite database and patch ``database.DB_NAME``."""
    db_file = tmp_path / "test_mygpt.db"
    db_str = str(db_file)

    import database
    monkeypatch.setattr(database, "DB_NAME", db_str)

    conn = sqlite3.connect(db_str)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            project_id INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            message TEXT
        );
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_key TEXT UNIQUE,
            memory_value TEXT,
            user_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            importance INTEGER DEFAULT 3,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

    yield db_str


@pytest.fixture
def app(tmp_db):
    """Return a FastAPI app wired to a test database."""
    import app as app_module
    return app_module.app


@pytest.fixture
def client(app):
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def test_user(tmp_db):
    """Insert a test user directly into the database."""
    import bcrypt
    from database import get_connection

    password = "testpass123"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
    """, ("Test User", "test@example.com", password_hash))
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {"id": user_id, "email": "test@example.com", "password": password}


@pytest.fixture
def auth_headers(client, test_user):
    """Return auth headers with a valid JWT for ``test_user``."""
    response = client.post(
        "/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
