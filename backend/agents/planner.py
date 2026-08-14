import re

def decide(user_message: str):
    """
    Intelligent planner that analyzes user intent and decides which tools/actions are required.
    Returns a set or primary action name.
    """
    message = user_message.lower().strip()

    # 1. Python Code Execution / Calculations / Algorithms
    CODE_KEYWORDS = [
        "calculate", "compute", "run python", "execute python", "python script",
        "solve math", "code interpreter", "evaluate", "factorial", "fibonacci",
        "sum of", "square root", "standard deviation", "simulated", "data analysis"
    ]
    if any(kw in message for kw in CODE_KEYWORDS) or re.search(r"```python[\s\S]*?```", user_message):
        return "python"

    # 2. Real-Time Date / Clock / Time
    TIME_KEYWORDS = [
        "what time is it", "current time", "what is today's date", "today's date",
        "what day is today", "what day is it", "current date"
    ]
    if any(kw in message for kw in TIME_KEYWORDS):
        return "time"

    # 3. Web Search (Current facts, live events, documentation, news, weather, stock prices)
    WEB_KEYWORDS = [
        "latest", "today", "news", "current", "search", "weather",
        "price", "live", "recent", "who won", "score", "release date",
        "browse", "google", "lookup", "stock", "crypto"
    ]
    if any(word in message for word in WEB_KEYWORDS):
        return "web"

    # 4. Document / PDF RAG
    DOC_KEYWORDS = ["pdf", "document", "file", "uploaded", "paper", "resume", "cv", "contract"]
    if any(word in message for word in DOC_KEYWORDS):
        return "rag"

    # 5. Image / Vision
    if "image" in message or "picture" in message or "photo" in message:
        return "vision"

    # 6. Memory
    if any(k in message for k in ["remember", "who am i", "my name", "what do you know about me", "my preferences"]):
        return "memory"

    return "chat"

