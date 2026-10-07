import re

from database import get_all_memories


STOP_WORDS = {
    "what", "is", "the", "a", "an", "in", "on", "of", "for", "to",
    "my", "me", "you", "your", "i", "am", "do", "how", "why",
    "where", "who", "which", "are", "was", "were", "and", "or",
    "tell", "about", "can", "please"
}


_MEMORY_INTENT = re.compile(
    r"\b(?:remember|told|tell|name|college|school|job|project|"
    r"preference|prefer|like|favorite|live|work|study|goal|"
    r"skill|language|framework)\b",
    re.IGNORECASE,
)


def is_memory_relevant(
    question: str,
    action: str | None = None,
) -> bool:
    """Return whether long-term personal memory can help answer the request."""

    if action in {
        "current_info",
        "web",
        "web_research",
        "rag",
    }:
        return False

    return _MEMORY_INTENT.search(question) is not None


def _extract_keywords(question: str) -> list[str]:
    """
    Extract meaningful normalized keywords.
    """
    words = re.findall(r"[a-zA-Z0-9_]+", question.lower())

    return [
        word
        for word in words
        if word not in STOP_WORDS and len(word) > 2
    ]


def search_memories(
    question: str,
    user_id: int,
    action: str | None = None,
):
    if not is_memory_relevant(question, action):
        return []

    memories = get_all_memories(user_id)

    if not memories:
        return []

    keywords = _extract_keywords(question)

    if not keywords:
        return memories[:3]

    scored = []

    for memory in memories:
        memory_words = set(
            re.findall(
                r"[a-zA-Z0-9_]+",
                memory.lower(),
            )
        )

        score = len(memory_words.intersection(keywords))

        if score > 0:
            scored.append((score, memory))

    # Highest relevance first.
    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        memory
        for _, memory in scored
    ]