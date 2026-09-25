import re

from database import get_all_memories

STOP_WORDS = {
    "what", "is", "the", "a", "an", "in", "on", "of", "for", "to", "my", "me",
    "you", "your", "i", "am", "do", "how", "why", "where", "who", "which", "are",
    "was", "were", "and", "or", "tell", "about", "can", "please"
}

_MEMORY_INTENT = re.compile(
    r"\b(?:remember|told|tell|name|college|school|job|project|"
    r"preference|prefer|like|favorite|live|work|study)\b",
    re.IGNORECASE,
)


def is_memory_relevant(question: str, action: str | None = None) -> bool:
    """Return whether long-term personal memory can help answer the request."""
    if action in {"current_info", "web", "web_research", "rag"}:
        return False
    return _MEMORY_INTENT.search(question) is not None


def search_memories(question: str, user_id: int, action: str | None = None):

    if not is_memory_relevant(question, action):
        return []

    memories = get_all_memories(user_id)

    if not memories:
        return []

    question = question.lower()

    # Extract meaningful keywords excluding stop words
    keywords = [
        word.strip("?,.!").lower()
        for word in question.split()
        if word.strip("?,.!").lower() not in STOP_WORDS
        and len(word.strip("?,.!")) > 2
    ]

    if not keywords:
        return memories[:3]

    relevant = []

    for memory in memories:
        memory_words = {
            word.strip("?,.!:;()[]{}").lower()
            for word in memory.split()
        }
        if memory_words.intersection(keywords):
            relevant.append(memory)

    if relevant:
        return relevant
    return []