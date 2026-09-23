import re
from agents.memory_extractor import extract_memories
from agents.memory_search import search_memories
from agents.prompt_builder import build_prompt
from agents.tools import web_search, execute_python, get_current_time
from agents.planner import decide, ACTION_CHAT, ACTION_PYTHON, ACTION_TIME, ACTION_WEB, ACTION_RAG, ACTION_VISION, ACTION_IMAGE_GEN, ACTION_MEMORY, ACTION_CODE, ACTION_CODE_EXPLANATION, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH, ACTION_GENERAL_KNOWLEDGE, ACTION_MATH, ACTION_CREATIVE
from agents.sequence_detector import extract_sequence_from_message, detect_sequence_pattern, get_sequence_answer
from agents.rag_verifier import verify_rag_answer, extract_code_entities_from_context, is_answer_safe_for_context

from database import save_memory, get_history

# Personal markers that indicate the user is sharing information about themselves
_PERSONAL_MARKERS = re.compile(
    r"\b(i am|i'm|my name|call me|i live|i work|i study|i like|i prefer|"
    r"my favorite|i use|my job|my goal|my project|remember that|keep in mind|please remember)\b",
    re.IGNORECASE
)


def _extract_word_problem(message: str):
    """
    Deterministically extract a simple arithmetic expression from natural-language
    word problems. Returns a Python expression string (e.g. '5 - 2') or None.

    Only handles validated patterns with explicit integers and recognized
    operations. Never executes arbitrary text from the user.
    """
    msg = message.lower()

    # Pattern 1: "If I have N ... and give away M ... how many remain?"
    # Pattern 2: "I have N ... and give away M ... How many remain?"
    # Pattern 3: "There are N ... and I remove M"
    # Pattern 4: "Start with N and subtract M"
    # Pattern 5: "Start with N and take away M"
    # Pattern 6: "N apples ... give away M"
    # Pattern 7: "N items ... remove M"

    # Subtraction patterns
    sub_patterns = [
        # "I have 5 apples and give away 2"
        r"\b(?:i\s+(?:have|had|got|started\s+with|bought))\s+(\d+)\s+\w+\s+(?:and|then)\s+give\s+away\s+(\d+)",
        # "If I have 5 apples and give away 2"
        r"\bif\s+i\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
        # "There are 20 items and I remove 5"
        r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+i\s+remove\s+(\d+)",
        # "Start with 10 and subtract 4"
        r"\bstart\s+with\s+(\d+)\s+and\s+subtract\s+(\d+)",
        # "Start with 10 and take away 4"
        r"\bstart\s+with\s+(\d+)\s+and\s+take\s+away\s+(\d+)",
        # "I have 10 apples and give away 3"
        r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
        # "I have 10 and give away 3"
        r"\bi\s+have\s+(\d+)\s+and\s+give\s+away\s+(\d+)",
        # "10 apples and give away 3"
        r"\b(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",
    ]

    for pattern in sub_patterns:
        m = re.search(pattern, msg)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return f"{a} - {b}"

    # Addition patterns
    add_patterns = [
        # "I have 5 apples and get 3 more"
        r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+(?:get|add|receive)\s+(\d+)\s+more",
        # "Start with 10 and add 5"
        r"\bstart\s+with\s+(\d+)\s+and\s+add\s+(\d+)",
        # "There are 5 and 3 more are added"
        r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+(\d+)\s+more",
    ]

    for pattern in add_patterns:
        m = re.search(pattern, msg)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return f"{a} + {b}"

    # Multiplication patterns
    mul_patterns = [
        # "What is 3 times 4?"
        r"\bwhat\s+is\s+(\d+)\s+times\s+(\d+)",
        # "3 groups of 4"
        r"\b(\d+)\s+groups?\s+of\s+(\d+)",
    ]

    for pattern in mul_patterns:
        m = re.search(pattern, msg)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return f"{a} * {b}"

    return None


class Agent:
    """
    MyGPT Autonomous Agent Core.
    Orchestrates Memory, RAG, Web Search, Code Interpreter, and LLM reasoning.
    """

    def run(self, message: str, chat_id=None, user_id=None):
        # 1. Decide action / tools needed
        action = decide(message)
        tool_results = None
        direct_answer = None

        # 2. Extract and Persist Long-Term User Facts & Preferences
        # Only run when message contains first-person personal markers to
        # avoid polluting memory with every routine question.
        if _PERSONAL_MARKERS.search(message) and user_id is not None:
            facts = extract_memories(message)
            for fact in facts:
                save_memory(fact, user_id)
            if facts:
                print(f"[Memory] Saved {len(facts)} user fact(s): {facts}")

        # Keep very simple greetings as a plain user message to avoid
        # unnecessary prompt overhead.
        _SIMPLE_GREETINGS = {"hi", "hello", "hey", "hi there", "hello there"}
        if action in (ACTION_CHAT, ACTION_GENERAL_KNOWLEDGE, ACTION_CREATIVE) and message.lower().strip() in _SIMPLE_GREETINGS:
            return {
                "prompt": message,
                "history": [],
                "context": None,
                "memories": [],
                "action": action,
                "tool_results": None,
                "answer": None,
            }

        # Check for sequence questions first (deterministic reasoning)
        if action in (ACTION_CHAT, ACTION_GENERAL_KNOWLEDGE, ACTION_CREATIVE):
            seq_answer = get_sequence_answer(message)
            if seq_answer is not None:
                return {
                    "prompt": message,
                    "history": [],
                    "context": None,
                    "memories": [],
                    "action": "sequence",
                    "tool_results": None,
                    "answer": seq_answer,
                }

        # 3. Retrieve Contexts
        history = get_history(chat_id) if chat_id is not None else []
        memories = search_memories(message, user_id) if user_id is not None else []
        context = None
        rag_unavailable = False

        # Check RAG for rag, code_explanation actions (when user asks about uploaded files)
        if action in (ACTION_RAG, ACTION_CODE_EXPLANATION) and user_id is not None:
            try:
                from rag import search_pdf
                context = search_pdf(message, user_id)
            except ImportError:
                rag_unavailable = True
            # RAG excludes arbitrary chat history to prevent contamination.
            # Only clear history if we actually found relevant document context.
            # This preserves conversation history for follow-up questions when
            # no uploaded document matches the query.
            if context:
                history = []
            # For RAG queries with document context, suppress long-term memories
            # to prevent memory contamination of grounded answers.
            if context:
                memories = []

        # For non-greeting chat messages without history/memories, use plain prompt
        if action in (ACTION_CHAT, ACTION_GENERAL_KNOWLEDGE, ACTION_CREATIVE) and not history and not memories:
            return {
                "prompt": message,
                "history": [],
                "context": None,
                "memories": [],
                "action": action,
                "tool_results": None,
                "answer": None,
            }

        # 4. Execute Autonomous Tools Based on Intent
        if action in (ACTION_WEB, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH):
            print(f"[Agent Tool] Executing Web Search for: {message}")
            search_result = web_search(message, max_results=5)
            results = search_result["results"]
            if results:
                web_text = "\n\n".join([
                    f"**{item['title']}**\n{item['body']}\nSource: {item['link']}"
                    for item in results
                ])
                if action == ACTION_CURRENT_INFO:
                    tool_results = (
                        f"CURRENT INFORMATION SEARCH RESULTS (use these for up-to-date facts):\n{web_text}\n\n"
                        f"IMPORTANT: Base your answer ONLY on the search results above. "
                        f"Cite sources with [Source: URL] format. "
                        f"Do NOT use your training knowledge for current prices, rates, weather, or news. "
                        f"If the search results don't contain the answer, say so honestly."
                    )
                elif action == ACTION_WEB_RESEARCH:
                    tool_results = (
                        f"WEB RESEARCH RESULTS:\n{web_text}\n\n"
                        f"Synthesize information from the sources above. "
                        f"Cite sources with [Source: URL] format. "
                        f"Distinguish between retrieved facts and your analysis."
                    )
                else:
                    tool_results = f"Web Search Results:\n{web_text}"
                if search_result.get("reformulated"):
                    tool_results += (
                        f"\n\n[Search note: original query was reformulated to "
                        f"\"{search_result['final_query']}\" because the original "
                        f"query contained a premise that may be incorrect.]"
                    )
                # Add debug metadata
                tool_results += (
                    f"\n\n[Debug: original_query={search_result['original_query']!r}, "
                    f"final_query={search_result['final_query']!r}, "
                    f"reformulated={search_result['reformulated']}, "
                    f"reason={search_result['reformulation_reason']!r}, "
                    f"total_found={search_result['total_found']}, "
                    f"returned={search_result['returned']}]"
                )
            else:
                if action == ACTION_CURRENT_INFO:
                    tool_results = (
                        "Web search returned no results for this current information query. "
                        "Do not fabricate current prices, rates, or values. "
                        "Inform the user that current information could not be verified."
                    )
                else:
                    tool_results = "Web search returned no results."

        elif action == ACTION_PYTHON:
            print(f"[Agent Tool] Executing Python Code Interpreter...")
            # Check if user provided explicit Python code
            code_match = re.search(r"```(?:python)?\s*([\s\S]*?)```", message, re.IGNORECASE)
            if code_match:
                code_to_run = code_match.group(1).strip()
            else:
                # If user asked a calculation like 'calculate 15% of 850' or '2**100'
                math_match = re.search(r"(?:calculate|compute|solve|eval|what is)\s+([0-9\+\-\*\/\^\(\)\.\s\%]+)", message, re.IGNORECASE)
                if math_match:
                    expr = math_match.group(1).strip().replace("^", "**")
                    code_to_run = f"print({expr})"
                else:
                    # Try deterministic word-problem extraction
                    # (e.g. "If I have 5 apples and give away 2, how many remain?")
                    wp_expr = _extract_word_problem(message)
                    if wp_expr is not None:
                        code_to_run = f"print({wp_expr})"
                    else:
                        code_to_run = None

            if code_to_run:
                exec_result = execute_python(code_to_run)
                if exec_result["success"]:
                    tool_results = f"Executed Python Code:\n```python\n{code_to_run}\n```\n\nOutput / Result:\n{exec_result['stdout']}"
                    if not code_match:
                        direct_answer = exec_result["stdout"]
                else:
                    tool_results = f"Code execution error (exit code {exec_result['exit_code']}):\n{exec_result['stderr'] or exec_result['stdout']}"
                if not code_match:
                    direct_answer = exec_result["stdout"]
            else:
                tool_results = "Python code interpreter ready. (No explicit executable snippet parsed)."

        elif action == ACTION_TIME:
            current_clock = get_current_time()
            tool_results = f"System Real-Time Clock: {current_clock}"
            direct_answer = current_clock

        elif action in (ACTION_RAG, ACTION_CODE_EXPLANATION):
            # Context is already fetched from search_pdf above.
            # Add a note so the prompt builder knows to emphasize document context.
            if rag_unavailable:
                tool_results = "Document retrieval is unavailable because the backend document dependencies are not installed."
            elif context:
                tool_results = "Document context retrieved from uploaded files — answer based on the document content above."
            else:
                # No relevant uploaded-file context was found.
                # Fall back to ordinary chat so the question is still answered
                # instead of being dropped or answered from unrelated context.
                tool_results = None
                context = None
                action = ACTION_CHAT

        elif action == ACTION_IMAGE_GEN:
            # Generate image using Gemini
            try:
                from gemini import generate_image
                image_b64 = generate_image(message)
                tool_results = f"Generated image based on: {message}"
                direct_answer = f"![Generated Image](data:image/png;base64,{image_b64})"
            except Exception as e:
                tool_results = f"Image generation failed: {str(e)}"
                direct_answer = "I'm sorry, I couldn't generate that image. Please try again."

        elif action == ACTION_CODE:
            # Code generation - will use stronger model via LLM routing
            # No tool execution needed, just pass to LLM with code generation prompt
            tool_results = (
                "CODE GENERATION REQUEST:\n"
                "Generate complete, compilable, production-quality code.\n"
                "Requirements:\n"
                "- Use the exact programming language requested\n"
                "- Include all necessary imports\n"
                "- Use meaningful variable/class/method names\n"
                "- Handle edge cases appropriately\n"
                "- Avoid unused variables or unnecessary imports\n"
                "- Provide complete code (not snippets) unless explicitly asked for a fragment\n"
                "- Include a brief explanation after the code if appropriate\n"
                "- Format code blocks with proper language tags\n"
            )

        elif action == ACTION_CODE_EXPLANATION:
            # Code explanation - may use RAG context if files uploaded
            if context:
                tool_results = (
                    "CODE EXPLANATION REQUEST:\n"
                    "Explain the previously provided code from uploaded documents.\n"
                    "Requirements:\n"
                    "- Explain line by line or section by section as requested\n"
                    "- Reference actual code from the document context\n"
                    "- Do NOT invent code that isn't in the context\n"
                    "- If context doesn't contain the answer, say so honestly\n"
                )
            else:
                # No uploaded file context - check conversation history for code
                tool_results = (
                    "CODE EXPLANATION REQUEST:\n"
                    "Explain code from conversation history.\n"
                    "Requirements:\n"
                    "- Reference the actual code from previous messages\n"
                    "- Explain line by line or section by section as requested\n"
                    "- Do NOT generate new unrelated code\n"
                )

        # 5. Assemble Structured Context Prompt
        prompt = build_prompt(
            question=message,
            history=history,
            memories=memories,
            context=context,
            tool_results=tool_results
        )

        return {
            "prompt": prompt,
            "history": history,
            "context": context,
            "memories": memories,
            "action": action,
            "tool_results": tool_results,
            "answer": direct_answer,
        }