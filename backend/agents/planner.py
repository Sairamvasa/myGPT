import re

# Action categories for the routing system
ACTION_CHAT = "chat"
ACTION_PYTHON = "python"
ACTION_TIME = "time"
ACTION_WEB = "web"
ACTION_RAG = "rag"
ACTION_VISION = "vision"
ACTION_IMAGE_GEN = "image_gen"
ACTION_MEMORY = "memory"
ACTION_CODE = "code"
ACTION_CODE_EXPLANATION = "code_explanation"
ACTION_CURRENT_INFO = "current_info"
ACTION_WEB_RESEARCH = "web_research"
ACTION_GENERAL_KNOWLEDGE = "general_knowledge"
ACTION_MATH = "math"
ACTION_CREATIVE = "creative"


def decide(user_message: str):
    """
    Intelligent planner that analyzes user intent and decides which tools/actions are required.
    Returns a primary action name from the predefined categories.
    """
    message = user_message.lower().strip()

    def contains_phrase(phrases):
        return any(
            re.search(rf"\b{re.escape(phrase)}\b", message)
            for phrase in phrases
        )

    # 0. Explicit code execution with fences or "run python" keywords
    CODE_EXEC_KEYWORDS = [
        "run python", "execute python", "python script",
        "code interpreter", "solve math", "evaluate", "factorial", "fibonacci",
        "sum of", "square root", "standard deviation", "simulated", "data analysis"
    ]
    # But don't match if it's a code generation request
    if (any(kw in message for kw in CODE_EXEC_KEYWORDS) or re.search(r"```python[\s\S]*?```", user_message)):
        # Check if it's actually a code generation request first
        CODE_GEN_PHRASES = [
            "write a", "create a", "generate a", "implement a", "build a",
            "code for", "program for", "script for", "function for",
            "how to write", "how to create", "how to implement",
            "write code", "create code", "generate code",
        ]
        is_code_gen = any(contains_phrase([p]) for p in CODE_GEN_PHRASES)
        if not is_code_gen:
            return ACTION_PYTHON

    # 1. Real-Time Date / Clock / Time (checked early)
    TIME_KEYWORDS = [
        "what time is it", "current time", "what is today's date", "today's date",
        "what day is today", "what day is it", "current date", "what is the date",
        "what is the time"
    ]
    if contains_phrase(TIME_KEYWORDS):
        return ACTION_TIME

    # 2. Current Information - specific real-time queries (before general web)
    CURRENT_INFO_PHRASES = [
        "today's price", "todays price", "today price", "price today",
        "current price", "current rate", "latest price", "live price",
        "today's weather", "current weather", "weather today",
        "current bitcoin", "current crypto", "bitcoin price", "crypto price",
        "current stock", "stock price", "live score", "match score",
        "petrol price", "diesel price", "fuel price", "gas price",
        "gold price", "silver price", "commodity price",
        "exchange rate", "currency rate",
    ]
    if contains_phrase(CURRENT_INFO_PHRASES):
        return ACTION_CURRENT_INFO

    # General freshness routing: a request with a freshness marker and a
    # factual/current-data subject must use the guarded live-search path.
    freshness_marker = re.search(
        r"\b(?:today|current|latest|now|recent|live)\b",
        message,
    )
    current_subject = re.search(
        r"\b(?:price|prices|news|weather|stock|stocks|"
        r"exchange\s+rate|currency\s+rate|events?|petrol|diesel|"
        r"fuel|bitcoin|crypto|score|scores)\b",
        message,
    )
    if (
        freshness_marker
        and current_subject
        and not re.search(r"\b(?:latest|recent)\s+\w*\s*news\b", message)
    ):
        return ACTION_CURRENT_INFO

    # 3. Web Research - broader research queries (before general web)
    WEB_RESEARCH_PHRASES = [
        "latest news", "recent news", "breaking news", "news about",
        "research", "find information about", "look up", "search for",
        "what happened", "current events", "recent developments",
        "latest developments", "news on",
        "what are the latest",
    ]
    # Also check for "latest X news" pattern
    if contains_phrase(WEB_RESEARCH_PHRASES) or re.search(r"\blatest\s+\w+\s+news\b", message):
        return ACTION_WEB_RESEARCH

    # 4. Code Generation - detect requests to write/generate code
    CODE_GEN_PHRASES = [
        "write a", "create a", "generate a", "implement a", "build a",
        "code for", "program for", "script for", "function for",
        "how to write", "how to create", "how to implement",
        "write code", "create code", "generate code",
    ]
    if contains_phrase(CODE_GEN_PHRASES):
        # Check if it's specifically asking for code in a language
        _LANG_PATTERNS = [
            r"\b(in|using|with)\s+(python|java|javascript|typescript|c\+\+|c#|go|rust|ruby|php|swift|kotlin|scala)\b",
            r"\b(python|java|javascript|typescript|c\+\+|c#|go|rust|ruby|php|swift|kotlin|scala)\s+(code|program|script|function)\b",
        ]
        for pattern in _LANG_PATTERNS:
            if re.search(pattern, message):
                return ACTION_CODE
        # General code generation request
        return ACTION_CODE

    # 5. Code Explanation - detect requests to explain existing code (before RAG)
    CODE_EXPLAIN_PHRASES = [
        "explain this code", "explain the code", "explain how this code works",
        "review this code", "analyze this code", "what does this code do",
        "how does this code work", "what does this function do",
        "what does this script do", "what does this file do",
        "walk through this code", "step through this code",
        "explain line by line", "explain each line",
    ]
    if contains_phrase(CODE_EXPLAIN_PHRASES):
        return ACTION_CODE_EXPLANATION

    # 6. Code-execution / code-reasoning intent -> python (before RAG to catch "what is the output of" with code)
    _CODE_PATTERN = re.compile(
        r"(?:"
        r"\bdef\s+\w+\s*\("           # def foo(
        r"|\bprint\s*\("               # print(
        r"|\bimport\s+\w+"             # import foo
        r"|\bfrom\s+\w+\s+import\b"    # from foo import bar
        r"|\b\w+\s*=\s*[\d'\"]"        # x = 10 or x = 'hello'
        r"|\bfor\s+\w+\s+in\b"         # for i in
        r"|\bwhile\s+\w+"              # while x
        r"|\bif\s+\w+\s*[:=]"          # if x:
        r"|\breturn\s+\w"              # return x
        r")",
        re.IGNORECASE
    )

    _CODE_EXEC_PHRASES = [
        "what is the output",
        "what does this output",
        "run this code",
        "run this python",
        "run this python code",
        "run it",
        "execute this code",
        "execute this python",
        "execute this python code",
        "execute it",
    ]

    _CODE_EXEC_EXTRA_PATTERNS = [
        re.compile(r"what\s+does\s+this\s+(?:python\s+)?code\s+output", re.IGNORECASE),
        re.compile(r"what\s+does\s+this\s+(?:python\s+)?script\s+output", re.IGNORECASE),
        re.compile(r"what\s+is\s+the\s+output\s+of", re.IGNORECASE),
        re.compile(r"(?:^|\n)\s*execute\s*:", re.IGNORECASE),
    ]

    _CODE_EXEC_PHRASES_COMPILED = [
        re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE)
        for p in _CODE_EXEC_PHRASES
    ]

    _has_code = _CODE_PATTERN.search(message) is not None
    _has_exec_intent = (
        any(p.search(message) for p in _CODE_EXEC_PHRASES_COMPILED)
        or any(p.search(message) for p in _CODE_EXEC_EXTRA_PATTERNS)
    )

    # Also detect fenced code blocks without the "python" language tag
    _has_code_fence = re.search(r"```[\s\S]*?```", user_message) is not None

    if (_has_code and _has_exec_intent) or _has_code_fence:
        return ACTION_PYTHON

    # 7. Document / PDF RAG
    DOC_KEYWORDS = [
        "pdf", "document", "file", "uploaded", "paper", "resume", "cv", "contract",
        "find any problems",
        "problems in this code", "bug in this", "error in this code",
        "what is in the file", "what is in the document", "what does the file say",
        "what does the document say", "summarize the file", "summarize the document",
        "project owner", "project developer", "who wrote this", "who created this",
        "about the project", "about the file", "about the document",
    ]
    contextual_result_question = re.search(
        r"\b(?:what|how|why|where|which)\b.*\b(?:output|result|return(?:s)?|value)\b",
        message,
    )
    if contains_phrase(DOC_KEYWORDS) or contextual_result_question:
        return ACTION_RAG

    # 7. Factual questions where freshness matters -> web
    FRESH_FACT_PHRASES = [
        "capital of",
        "what is the capital",
        "who is the president",
        "who is the prime minister",
        "who is the mayor",
        "current population",
        "what is the population of",
    ]
    if contains_phrase(FRESH_FACT_PHRASES):
        return ACTION_WEB

    # 8. General Web Search
    WEB_PHRASES = [
        "weather", "stock", "stocks",
        "crypto", "bitcoin", "ethereum", "cryptocurrency", "live score", "who won", "release date", "search the web",
        "browse the web", "google", "current crypto", "current ethereum",
        "petrol prices", "diesel prices", "fuel prices", "gas prices",
        "gold price", "silver price", "commodity price",
        "product price", "market price", "retail price",
        "cricket score", "match score", "live match",
    ]
    if contains_phrase(WEB_PHRASES):
        return ACTION_WEB

    # 9. Image / Vision
    if contains_phrase(["image", "picture", "photo"]):
        return ACTION_VISION

    # 10. Image Generation
    IMAGE_GEN_PHRASES = [
        "generate an image",
        "generate an image of",
        "create an image",
        "create an image of",
        "draw an image",
        "draw an image of",
        "make an image",
        "make an image of",
        "generate a picture",
        "generate a picture of",
        "create a picture",
        "create a picture of",
        "draw a picture",
        "draw a picture of",
        "make a picture",
        "make a picture of",
        "generate an illustration",
        "create an illustration",
        "draw an illustration",
    ]
    if contains_phrase(IMAGE_GEN_PHRASES):
        return ACTION_IMAGE_GEN

    # 11. Memory
    if contains_phrase([
        "remember", "who am i", "my name", "what do you know about me",
        "my preferences", "my college", "my school", "my job",
        "my project", "what did i tell you",
    ]):
        return ACTION_MEMORY

    # 12. Direct arithmetic / calculation intent -> python
    _PROGRAMMING_CONTEXT = re.compile(
        r"\b(mean|operator|syntax|semantic|function|method|class|"
        r"import|module|library|package|loop|variable|string|list|"
        r"dictionary|tuple|set|boolean|integer|float|type|debug|error|"
        r"bug|exception|traceback|documentation|docstring|code|script|"
        r"program|programming|algorithm)\b",
        re.IGNORECASE
    )

    _ARITH_EXPR = re.compile(
        r"\d+\s*[\+\-\*\/\%]\s*\d+"
    )

    _PERCENT_CALC = re.compile(
        r"\d+\s*%\s+of\s+\d+"
    )

    _WORD_PROBLEM = re.compile(
        r"\b(apples?|oranges?|bananas?|items?|objects?|people?|persons?|"
        r"give\s+away|left\s+with|remaining|remain|total\s+of|how\s+many|"
        r"how\s+much)\b",
        re.IGNORECASE
    )

    _HOW_MUCH_IS = re.compile(
        r"how\s+much\s+is\s+.+"
    )

    _HAS_NUMBER = re.compile(r"\d+")

    is_arithmetic = (
        _ARITH_EXPR.search(message) is not None
        or _PERCENT_CALC.search(message) is not None
        or _HOW_MUCH_IS.search(message) is not None
    )

    is_word_problem = (
        _WORD_PROBLEM.search(message) is not None
        and _HAS_NUMBER.search(message) is not None
        and not _PROGRAMMING_CONTEXT.search(message)
    )

    if is_arithmetic and not _PROGRAMMING_CONTEXT.search(message):
        return ACTION_PYTHON

    if is_word_problem:
        return ACTION_PYTHON

    # 13. Math - pure math questions
    if (re.search(r"\b(calculate|compute|solve|what is)\s+\d+", message)
        or re.search(r"\d+\s*[\+\-\*\/\^]\s*\d+", message)):
        if not re.search(r"\b(code|program|script|function|write|create|generate)\b", message):
            return ACTION_MATH

    # 15. General Knowledge - stable facts
    GENERAL_KNOWLEDGE_PHRASES = [
        "what is", "who is", "where is", "when was", "how to",
        "define", "definition of", "explain", "describe",
        "who wrote", "who created", "who invented", "who discovered",
    ]
    # But exclude if it matches current info or code patterns
    if (any(message.startswith(p) for p in ["what is ", "who is ", "where is ", "when was ", "how to ", "who wrote ", "who created ", "who invented ", "who discovered "]) 
        and not any(p in message for p in ["price", "weather", "stock", "crypto", "bitcoin", "rate", "news"])
        and not re.search(r"\b(code|program|script|function|java|python|javascript)\b", message)):
        return ACTION_GENERAL_KNOWLEDGE

    # 16. Creative - creative writing
    CREATIVE_PHRASES = [
        "write a story", "write a poem", "create a story", "write an essay",
        "write a blog", "creative writing", "write a joke", "tell a joke",
        "tell me a joke",
    ]
    if contains_phrase(CREATIVE_PHRASES):
        return ACTION_CREATIVE

    return ACTION_CHAT