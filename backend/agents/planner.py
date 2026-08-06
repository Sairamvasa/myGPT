def decide(user_message):

    message = user_message.lower()

    # Memory
    if (
        "remember" in message
        or "my name is" in message
        or "what is my name" in message
        or "who am i" in message
    ):
        return "memory"

    # PDF
    if "pdf" in message:
        return "rag"

    # Vision
    if "image" in message:
        return "vision"

    # Web
    WEB_KEYWORDS = [
    "latest",
    "today",
    "news",
    "current",
    "search",
    "weather",
    "price",
    "live",
    "recent"
]

    if any(word in message for word in WEB_KEYWORDS):
        return "web"
