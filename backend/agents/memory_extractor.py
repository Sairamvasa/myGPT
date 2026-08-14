import re

def extract_memories(message: str):
    """
    Extract useful facts and preferences from the user's message.
    Returns a list of memory facts.
    """
    memories = []

    patterns = [
        (r"my name is (.+)", "User's name is {}"),
        (r"call me (.+)", "User's name is {}"),
        (r"i am from (.+)", "User is from {}"),
        (r"i live in (.+)", "User lives in {}"),
        (r"i am a (.+)", "User is a {}"),
        (r"i study at (.+)", "User studies at {}"),
        (r"i work at (.+)", "User works at {}"),
        (r"i work as a (.+)", "User works as a {}"),
        (r"my job is (.+)", "User's job is {}"),
        (r"my favorite language is (.+)", "User's favorite language is {}"),
        (r"my favorite framework is (.+)", "User's favorite framework is {}"),
        (r"i prefer (.+)", "User prefers {}"),
        (r"i like (.+)", "User likes {}"),
        (r"my project is (.+)", "User's project is {}"),
        (r"my goal is (.+)", "User's goal is {}"),
        (r"remember that (.+)", "User note: {}"),
        (r"keep in mind that (.+)", "User note: {}"),
        (r"please remember (.+)", "User note: {}"),
    ]

    text = message.lower().strip()

    for pattern, template in patterns:
        match = re.search(pattern, text)

        if match:
            value = match.group(1).strip().strip(".,!?;:")
            # If the user added extra conversational clauses after a comma/period, isolate the main fact
            if "," in value:
                value = value.split(",")[0].strip()

            if value and len(value) > 1:
                # Format value nicely
                fact = template.format(value.capitalize())
                if fact not in memories:
                    memories.append(fact)

    return memories