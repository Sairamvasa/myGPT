from database import get_all_memories

STOP_WORDS = {
    "what", "is", "the", "a", "an", "in", "on", "of", "for", "to", "my", "me",
    "you", "your", "i", "am", "do", "how", "why", "where", "who", "which", "are",
    "was", "were", "and", "or", "tell", "about", "can", "please"
}


def search_memories(question: str, user_id: int):

    memories = get_all_memories(user_id)

    if not memories:
        return []

    question = question.lower()

    # Extract meaningful keywords excluding stop words
    keywords = [
        word.strip("?,.!")
        for word in question.split()
        if word.strip("?,.!") not in STOP_WORDS and len(word.strip("?,.!")) > 2
    ]

    if not keywords:
        return memories[:3]

    relevant = []

    for memory in memories:
        text = memory.lower()

        for keyword in keywords:
            if keyword in text:
                relevant.append(memory)
                break

    if relevant:
        return relevant

    return memories[:3]