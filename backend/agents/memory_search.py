from database import get_all_memories


def search_memories(question: str):

    memories = get_all_memories()

    question = question.lower()

    relevant = []

    keywords = question.split()

    for memory in memories:

        text = memory.lower()

        for keyword in keywords:

            if keyword in text:
                relevant.append(memory)
                break

    if relevant:
        return relevant

    return memories[:5]