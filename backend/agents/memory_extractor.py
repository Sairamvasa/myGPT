import re

def extract_memories(message: str):
    """
    Extract useful facts from the user's message.
    Returns a list of memory facts.
    """

    memories = []

    patterns = [
        (r"my name is (.+)", "User's name is {}"),
        (r"i am from (.+)", "User is from {}"),
        (r"i live in (.+)", "User lives in {}"),
        (r"i study at (.+)", "User studies at {}"),
        (r"i work at (.+)", "User works at {}"),
        (r"my favorite language is (.+)", "User's favorite language is {}"),
        (r"my project is (.+)", "User's project is {}"),
    ]

    text = message.lower()

    for pattern, template in patterns:
        match = re.search(pattern, text)

        if match:
            value = match.group(1).strip()

            memories.append(
                template.format(value.title())
            )

    return memories