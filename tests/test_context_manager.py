"""Tests for backend/agents/context_manager.py.

All tests use injected/mocked retrievers — no external APIs, no database.
"""

import pytest

from agents.context_manager import (
    ContextItem,
    ContextBundle,
    rank_context,
    deduplicate_context,
    limit_context,
    format_context,
    verify_scope,
    build_context,
    DEFAULT_BUDGET,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(source: str, content: str, score: float = 0.0, **meta) -> ContextItem:
    return ContextItem(source=source, content=content, score=score, metadata=meta)


# ---------------------------------------------------------------------------
# 1. Conversation context
# ---------------------------------------------------------------------------

def test_conversation_context():
    bundle = ContextBundle(
        conversation=[
            _item("conversation", "User: hello", 1.0, role="user", user_id=1),
            _item("conversation", "Assistant: hi", 1.0, role="assistant", user_id=1),
        ],
    )
    formatted = format_context(bundle)
    assert len(formatted["history"]) == 2
    assert formatted["history"][0] == ("user", "User: hello")
    assert formatted["history"][1] == ("assistant", "Assistant: hi")


# ---------------------------------------------------------------------------
# 2. Memory context
# ---------------------------------------------------------------------------

def test_memory_context():
    bundle = ContextBundle(
        memories=[
            _item("memory", "User likes Python", 0.9, user_id=1),
            _item("memory", "User lives in London", 0.7, user_id=1),
        ],
    )
    formatted = format_context(bundle)
    assert "User likes Python" in formatted["memories"]
    assert "User lives in London" in formatted["memories"]


# ---------------------------------------------------------------------------
# 3. RAG context
# ---------------------------------------------------------------------------

def test_rag_context():
    bundle = ContextBundle(
        rag=[
            _item("rag", "Document chunk A", 0.8, doc_source="doc1.pdf", user_id=1, scope="user"),
            _item("rag", "Document chunk B", 0.6, doc_source="doc1.pdf", user_id=1, scope="user"),
        ],
    )
    formatted = format_context(bundle)
    assert "Document chunk A" in formatted["context"]
    assert "Document chunk B" in formatted["context"]


# ---------------------------------------------------------------------------
# 4. Project context
# ---------------------------------------------------------------------------

def test_project_context():
    bundle = ContextBundle(
        project=[
            _item("project", "Project spec v1", 0.95, project_id=42, user_id=1, scope="project"),
        ],
    )
    formatted = format_context(bundle)
    assert "Project spec v1" in formatted["context"]


# ---------------------------------------------------------------------------
# 5. Ranking
# ---------------------------------------------------------------------------

def test_ranking_priority_order():
    items = [
        _item("tool", "tool result", 0.9),
        _item("conversation", "chat msg", 0.9),
        _item("rag", "doc chunk", 0.9),
        _item("memory", "fact", 0.9),
        _item("project", "project doc", 0.9),
        _item("recent", "recent msg", 0.9),
    ]
    ranked = rank_context(items)
    sources = [it.source for it in ranked]
    assert sources == ["conversation", "recent", "project", "rag", "memory", "tool"]


def test_ranking_score_within_source():
    items = [
        _item("rag", "low score", 0.1),
        _item("rag", "high score", 0.9),
        _item("rag", "mid score", 0.5),
    ]
    ranked = rank_context(items)
    scores = [it.score for it in ranked]
    assert scores == [0.9, 0.5, 0.1]


def test_ranking_deterministic_tie_break():
    items = [
        _item("rag", "same content", 0.5),
        _item("rag", "same content", 0.5),
    ]
    ranked = rank_context(items)
    assert len(ranked) == 2
    assert ranked[0].score == ranked[1].score


# ---------------------------------------------------------------------------
# 6. Deduplication
# ---------------------------------------------------------------------------

def test_deduplicate_removes_identical():
    items = [
        _item("rag", "duplicate content", 0.9),
        _item("rag", "duplicate content", 0.5),
        _item("rag", "unique content", 0.7),
    ]
    deduped = deduplicate_context(items)
    assert len(deduped) == 2
    assert deduped[0].score == 0.9  # highest-ranked kept


def test_deduplicate_normalizes_whitespace():
    items = [
        _item("rag", "hello   world", 0.9),
        _item("rag", "hello world", 0.5),
    ]
    deduped = deduplicate_context(items)
    assert len(deduped) == 1


# ---------------------------------------------------------------------------
# 7. Context size limiting
# ---------------------------------------------------------------------------

def test_limit_context_total_budget():
    big = "x" * 5000
    bundle = ContextBundle(
        conversation=[_item("conversation", big, 1.0)],
        rag=[_item("rag", big, 1.0)],
    )
    limited = limit_context(bundle, {"_total": 6000, "conversation": 4000, "rag": 4000})
    total = sum(len(it.content) for it in limited.all_items())
    assert total <= 6000


def test_limit_context_per_source_budget():
    big = "x" * 5000
    bundle = ContextBundle(
        rag=[_item("rag", big, 1.0)],
    )
    limited = limit_context(bundle, {"rag": 2000, "_total": 10000})
    assert sum(len(it.content) for it in limited.rag) <= 2000


def test_limit_context_empty():
    bundle = ContextBundle()
    limited = limit_context(bundle)
    assert limited.total_items == 0


# ---------------------------------------------------------------------------
# 8. User isolation
# ---------------------------------------------------------------------------

def test_verify_scope_user_mismatch():
    item = _item("memory", "secret", 0.9, user_id=2)
    assert verify_scope(item, user_id=1) is False


def test_verify_scope_user_match():
    item = _item("memory", "own fact", 0.9, user_id=1)
    assert verify_scope(item, user_id=1) is True


def test_verify_scope_no_user_metadata_accepted():
    item = _item("rag", "public chunk", 0.9)
    assert verify_scope(item, user_id=1) is True


def test_build_context_rejects_cross_user_memory():
    def fake_memory_retriever(query, user_id):
        return [
            ("own memory", {"user_id": user_id}),
            ("other memory", {"user_id": 999}),
        ]

    bundle = build_context(
        user_id=1,
        query="test",
        retrievers={"memory": fake_memory_retriever},
    )
    contents = [it.content for it in bundle.memories]
    assert "own memory" in contents
    assert "other memory" not in contents


# ---------------------------------------------------------------------------
# 9. Project isolation
# ---------------------------------------------------------------------------

def test_verify_scope_project_mismatch():
    item = _item("project", "project data", 0.9, project_id=2, user_id=1)
    assert verify_scope(item, user_id=1, project_id=1) is False


def test_verify_scope_project_match():
    item = _item("project", "project data", 0.9, project_id=1, user_id=1)
    assert verify_scope(item, user_id=1, project_id=1) is True


def test_build_context_rejects_cross_project_rag():
    def fake_rag_retriever(query, user_id, project_id):
        return [
            ("own project doc", {"project_id": project_id, "user_id": user_id}),
            ("other project doc", {"project_id": 999, "user_id": user_id}),
        ]

    bundle = build_context(
        user_id=1,
        query="test",
        project_id=1,
        retrievers={"rag": fake_rag_retriever},
    )
    contents = [it.content for it in bundle.rag]
    assert "own project doc" in contents
    assert "other project doc" not in contents


# ---------------------------------------------------------------------------
# 10. Empty context
# ---------------------------------------------------------------------------

def test_empty_context():
    bundle = ContextBundle()
    formatted = format_context(bundle)
    assert formatted["context"] == ""
    assert formatted["memories"] == []
    assert formatted["history"] == []
    assert formatted["tool_results"] == ""
    assert formatted["recent"] == []


def test_build_context_empty():
    bundle = build_context(user_id=1, query="test", retrievers={})
    assert bundle.total_items == 0


# ---------------------------------------------------------------------------
# 11. Deterministic output
# ---------------------------------------------------------------------------

def test_format_context_deterministic():
    bundle = ContextBundle(
        conversation=[
            _item("conversation", "msg A", 1.0, role="user"),
            _item("conversation", "msg B", 1.0, role="assistant"),
        ],
        memories=[_item("memory", "fact 1", 0.8)],
        rag=[_item("rag", "doc 1", 0.7)],
    )
    f1 = format_context(bundle)
    f2 = format_context(bundle)
    assert f1 == f2
    assert f1["history"] == [("user", "msg A"), ("assistant", "msg B")]
    assert f1["memories"] == ["fact 1"]
    assert f1["context"] == "doc 1"


def test_rank_context_deterministic():
    items = [
        _item("rag", "zebra", 0.5),
        _item("rag", "apple", 0.5),
        _item("conversation", "hello", 0.5),
    ]
    r1 = rank_context(items)
    r2 = rank_context(items)
    assert [it.content for it in r1] == [it.content for it in r2]


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_verify_scope_project_none_when_no_project_id():
    item = _item("project", "data", 0.9, project_id=5, user_id=1)
    assert verify_scope(item, user_id=1, project_id=None) is False


def test_verify_scope_project_none_matches():
    item = _item("project", "data", 0.9, user_id=1)
    assert verify_scope(item, user_id=1, project_id=None) is True


def test_deduplicate_preserves_order():
    items = [
        _item("rag", "first", 0.9),
        _item("rag", "second", 0.8),
        _item("rag", "first", 0.7),
    ]
    deduped = deduplicate_context(items)
    assert len(deduped) == 2
    assert deduped[0].content == "first"
    assert deduped[1].content == "second"


def test_limit_context_total_zero_budget():
    bundle = ContextBundle(
        conversation=[_item("conversation", "hello", 1.0)],
    )
    limited = limit_context(bundle, {"_total": 0, "conversation": 0})
    assert limited.total_items == 0


def test_format_context_project_first():
    bundle = ContextBundle(
        project=[_item("project", "PROJECT CONTENT", 0.9)],
        rag=[_item("rag", "RAG CONTENT", 0.8)],
    )
    formatted = format_context(bundle)
    assert formatted["context"].startswith("PROJECT CONTENT")
    assert "RAG CONTENT" in formatted["context"]


def test_build_context_with_chat_id(monkeypatch):
    def fake_history(chat_id):
        return [("user", "past message")]

    monkeypatch.setattr("database.get_history", fake_history)

    bundle = build_context(
        user_id=1,
        query="test",
        chat_id=10,
        retrievers={},
    )
    assert any("past message" in it.content for it in bundle.conversation)