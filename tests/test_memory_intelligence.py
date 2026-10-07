from agents.memory_extractor import (
    extract_memory_candidates,
    PROFILE,
    PREFERENCE,
    PROJECT,
    GOAL,
)


def test_structured_name_memory():
    memories = extract_memory_candidates(
        "My name is John"
    )

    assert len(memories) == 1
    assert memories[0].category == PROFILE
    assert memories[0].key == "name"
    assert "John" in memories[0].fact


def test_structured_preference_memory():
    memories = extract_memory_candidates(
        "I prefer Telugu explanations"
    )

    assert len(memories) == 1
    assert memories[0].category == PREFERENCE


def test_structured_project_memory():
    memories = extract_memory_candidates(
        "My project is an AI chatbot"
    )

    assert len(memories) == 1
    assert memories[0].category == PROJECT


def test_structured_goal_memory():
    memories = extract_memory_candidates(
        "My goal is to publish an IEEE paper"
    )

    assert len(memories) == 1
    assert memories[0].category == GOAL


def test_duplicate_candidates():
    memories = extract_memory_candidates(
        "My name is John. My name is John."
    )

    assert len(memories) == 1


def test_empty_message():
    memories = extract_memory_candidates("Hello")

    assert memories == []