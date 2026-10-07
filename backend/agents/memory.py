from database import (
    remember_memory,
    recall_memory,
    save_memory,
    get_all_memories,
)

from agents.memory_extractor import extract_memory_candidates


def remember(key, value, user_id):
    return remember_memory(key, value, user_id)


def recall(key, user_id):
    return recall_memory(key, user_id)


def remember_fact(
    fact: str,
    user_id: int,
    importance: int = 3,
):
    """
    Store a long-term fact using the existing persistent memory system.
    """
    if not fact or not fact.strip():
        return False

    importance = max(1, min(int(importance), 5))

    save_memory(
        fact.strip(),
        user_id=user_id,
        importance=importance,
    )

    return True


def extract_and_store_memories(
    message: str,
    user_id: int,
):
    """
    Extract structured memory candidates and persist them.

    Returns the candidates that were considered.
    """
    candidates = extract_memory_candidates(message)

    stored = []

    for candidate in candidates:
        remember_fact(
            candidate.fact,
            user_id=user_id,
            importance=candidate.importance,
        )

        stored.append(candidate)

    return stored


def get_user_memories(user_id: int):
    """
    Return all persistent memories for one user.
    """
    return get_all_memories(user_id)