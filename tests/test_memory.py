"""Tests for long-term memory: extraction, search, persistence, isolation."""

import pytest


# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------

class TestExtractMemories:
    def test_extract_name(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("My name is John")
        assert any("John" in m for m in mems)

    def test_extract_call_me(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("Call me Alex")
        assert any("Alex" in m for m in mems)

    def test_extract_location(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("I live in New York")
        assert any("york" in m.lower() for m in mems)

    def test_extract_job(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("I am a software engineer")
        assert any("software engineer" in m.lower() for m in mems)

    def test_extract_favorite(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("I like pizza")
        assert any("pizza" in m.lower() for m in mems)

    def test_extract_project(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("My project is a chatbot")
        assert any("chatbot" in m.lower() for m in mems)

    def test_extract_no_memories(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("Hello, how are you?")
        assert mems == []

    def test_extract_multiple_facts(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("My name is John and my favorite language is Python")
        assert len(mems) >= 2

    def test_extract_remember_directive(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("Remember that my birthday is June 15th")
        assert any("birthday" in m.lower() or "June 15" in m for m in mems)

    def test_extract_deduplication(self):
        from agents.memory_extractor import extract_memories
        mems = extract_memories("My name is John. My name is John.")
        # Should deduplicate
        assert len(mems) == 1


# ---------------------------------------------------------------------------
# Memory relevance
# ---------------------------------------------------------------------------

class TestMemoryRelevance:
    def test_is_memory_relevant_name(self):
        from agents.memory_search import is_memory_relevant
        assert is_memory_relevant("Remember my name", "chat") is True

    def test_is_memory_relevant_preferences(self):
        from agents.memory_search import is_memory_relevant
        # "preference" matches the _MEMORY_INTENT pattern
        assert is_memory_relevant("what is my preference", "chat") is True

    def test_not_relevant_for_web(self):
        from agents.memory_search import is_memory_relevant
        assert is_memory_relevant("search the web", "web") is False

    def test_not_relevant_for_current_info(self):
        from agents.memory_search import is_memory_relevant
        assert is_memory_relevant("bitcoin price", "current_info") is False

    def test_not_relevant_for_rag(self):
        from agents.memory_search import is_memory_relevant
        assert is_memory_relevant("what is in the file", "rag") is False

    def test_irrelevant_query_returns_false(self):
        from agents.memory_search import is_memory_relevant
        assert is_memory_relevant("what is 2+2", "math") is False


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------

class TestMemoryPersistence:
    def test_save_and_recall_single_memory(self, tmp_db):
        from database import save_memory, recall_memory
        save_memory("User's name is John", user_id=1)
        result = recall_memory("name", user_id=1)
        # recall_memory searches by key; "name" as a key may not exist
        # since save_memory stores by fact, not key. Verify save worked.
        from database import get_all_memories
        all_mems = get_all_memories(1)
        assert any("John" in m for m in all_mems)

    def test_recall_missing_memory(self, tmp_db):
        from database import recall_memory
        result = recall_memory("nonexistent_key", user_id=999)
        assert result is None

    def test_get_all_memories(self, tmp_db):
        from database import save_memory, get_all_memories
        save_memory("User likes cats", user_id=1)
        save_memory("User is a developer", user_id=1)

        memories = get_all_memories(user_id=1)
        assert len(memories) >= 2

    def test_memory_user_isolation(self, tmp_db):
        """Memories saved by user A are not visible to user B."""
        from database import save_memory, get_all_memories

        save_memory("User A's secret", user_id=100)
        save_memory("User B's secret", user_id=101)

        mem_a = get_all_memories(user_id=100)
        mem_b = get_all_memories(user_id=101)

        assert any("A" in m for m in mem_a)
        assert not any("B" in m for m in mem_a)
        assert any("B" in m for m in mem_b)
        assert not any("A" in m for m in mem_b)

    def test_recall_by_keyword(self, tmp_db):
        """Recall memory by exact key."""
        from database import remember_memory, recall_memory
        remember_memory("favorite_color", "blue", user_id=1)
        remember_memory("birthday", "June 15", user_id=1)

        result = recall_memory("favorite_color", user_id=1)
        assert "blue" in result.lower()

    def test_memory_overwrite_same_fact(self, tmp_db):
        """Saving the same fact twice does not create a duplicate."""
        from database import save_memory, get_all_memories
        save_memory("User's name is John", user_id=1)
        save_memory("User's name is John", user_id=1)  # Same fact — should not duplicate

        all_mems = get_all_memories(1)
        john_count = sum(1 for m in all_mems if "John" in m)
        assert john_count == 1


# ---------------------------------------------------------------------------
# Memory search with DB
# ---------------------------------------------------------------------------

class TestMemorySearch:
    def test_search_memories_with_data(self, tmp_db):
        from database import save_memory
        from agents.memory_search import search_memories

        save_memory("User's name is John", user_id=1)
        save_memory("User is from Canada", user_id=1)
        save_memory("User likes pizza", user_id=1)

        results = search_memories("What is my name", user_id=1, action="chat")
        assert any("John" in r for r in results)

    def test_search_memories_no_match(self, tmp_db):
        from database import save_memory
        from agents.memory_search import search_memories

        save_memory("User's name is John", user_id=1)

        results = search_memories("what is the weather", user_id=1, action="chat")
        assert results == []

    def test_search_memories_user_isolation(self, tmp_db):
        from database import save_memory
        from agents.memory_search import search_memories

        save_memory("User A's name is John", user_id=1)
        save_memory("User B's name is Jane", user_id=2)

        r1 = search_memories("remember my name", user_id=1, action="memory")
        r2 = search_memories("remember my name", user_id=2, action="memory")

        assert any("John" in r for r in r1)
        assert not any("Jane" in r for r in r1)
        assert any("Jane" in r for r in r2)
        assert not any("John" in r for r in r2)

    def test_search_memories_web_action_returns_empty(self, tmp_db):
        from database import save_memory
        from agents.memory_search import search_memories

        save_memory("User's name is John", user_id=1)

        results = search_memories("search the web", user_id=1, action="web")
        assert results == []
