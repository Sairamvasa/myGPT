import re

import time

from agents.result_collector import ResultCollector

from agents.result_verifier import verify_tool_result

from agents.tool_selector import select_tool

from agents.tool_validator import validate_tool_request

from agents.tool_permissions import (

    PermissionDecision,

    evaluate_tool_permission,

)

from agents.observations import tool_result_to_observation

from agents.tool_registry import ToolContext

from agents.tool_implementations import get_tool_registry

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



    # Subtraction patterns

    sub_patterns = [

        r"\b(?:i\s+(?:have|had|got|started\s+with|bought))\s+(\d+)\s+\w+\s+(?:and|then)\s+give\s+away\s+(\d+)",

        r"\bif\s+i\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",

        r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+i\s+remove\s+(\d+)",

        r"\bstart\s+with\s+(\d+)\s+and\s+subtract\s+(\d+)",

        r"\bstart\s+with\s+(\d+)\s+and\s+take\s+away\s+(\d+)",

        r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",

        r"\bi\s+have\s+(\d+)\s+and\s+give\s+away\s+(\d+)",

        r"\b(\d+)\s+\w+\s+and\s+give\s+away\s+(\d+)",

    ]



    for pattern in sub_patterns:

        m = re.search(pattern, msg)

        if m:

            a, b = int(m.group(1)), int(m.group(2))

            return f"{a} - {b}"



    # Addition patterns

    add_patterns = [

        r"\bi\s+have\s+(\d+)\s+\w+\s+and\s+(?:get|add|receive)\s+(\d+)\s+more",

        r"\bstart\s+with\s+(\d+)\s+and\s+add\s+(\d+)",

        r"\bthere\s+are\s+(\d+)\s+\w+\s+and\s+(\d+)\s+more",

    ]



    for pattern in add_patterns:

        m = re.search(pattern, msg)

        if m:

            a, b = int(m.group(1)), int(m.group(2))

            return f"{a} + {b}"



    # Multiplication patterns

    mul_patterns = [

        r"\bwhat\s+is\s+(\d+)\s+times\s+(\d+)",

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



    def run(self, message: str, chat_id=None, user_id=None, perf_context=None, project_id=None):

        started = time.perf_counter()

        tool_registry = get_tool_registry()

        tool_context = ToolContext(

            user_id=user_id,

            chat_id=chat_id,

            project_id=project_id,

        )

        result_collector = ResultCollector()

        # 1. Decide action / tools needed

        action = decide(message)

        if perf_context is not None:

            perf_context.routing_ms = (time.perf_counter() - started) * 1000

        tool_results = None

        direct_answer = None



        # 2. Extract and Persist Long-Term User Facts & Preferences

        # Skip extraction for math/general knowledge/chat to reduce TTFT

        if action not in (ACTION_MATH, ACTION_GENERAL_KNOWLEDGE) and _PERSONAL_MARKERS.search(message) and user_id is not None:

            if action in (ACTION_MEMORY,):

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

        retrieval_started = time.perf_counter()

        history = get_history(chat_id) if chat_id is not None else []

        # The API persists the current user turn before invoking the agent so

        # failures still leave a consistent conversation. Keep only prior

        # turns in the history section because the current request is added

        # explicitly by build_prompt().

        if history and history[-1] == ("user", message):

            history = history[:-1]



        memories = []

        if user_id is not None and action in (ACTION_MEMORY, ACTION_WEB_RESEARCH):

            memories = search_memories(message, user_id, action=action)



        context = None

        rag_unavailable = False



        contextual_followup = bool(

            re.search(

                r"\b(?:what|how|why|where|which|does|is|are|explain|describe)\b.*\b(?:this|that|it|here|there|output|result|return|returns|value|function|code|script|file)\b",

                message,

                re.IGNORECASE,

            )

        )



        # Check RAG for rag, code_explanation actions (when user asks about uploaded files)

        if (action in (ACTION_RAG, ACTION_CODE_EXPLANATION) or contextual_followup) and user_id is not None:

            try:

                from rag import search_pdf

            except ImportError:

                search_pdf = None



            # Project context takes precedence — project files are scoped to project_id

            if project_id is not None:

                try:

                    from rag import search_project_pdf

                    context = search_project_pdf(message, project_id)

                except ImportError:

                    context = None

            elif search_pdf is not None:

                context = search_pdf(message, user_id)

            else:

                rag_unavailable = True

            # RAG excludes arbitrary chat history to prevent contamination.

            # Only clear history if we actually found relevant document context.

            if context:

                history = []

            # For RAG queries with document context, suppress long-term memories

            # to prevent memory contamination of grounded answers.

            if context:

                memories = []

                if action in (ACTION_CHAT, ACTION_GENERAL_KNOWLEDGE, ACTION_CREATIVE):

                    action = ACTION_RAG



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

            selected_tool = select_tool(action)

            if selected_tool != "web_search":
                tool_results = "Tool selection mismatch: expected web_search."
            else:
                tool_args = {
                    "query": message,
                    "max_results": 5,
                }

                valid, validation_error = validate_tool_request(
                    tool_registry,
                    selected_tool,
                    tool_args,
                )

                if not valid:
                    tool_results = f"Tool validation failed: {validation_error}"
                else:
                    permission = evaluate_tool_permission(
                        tool_registry,
                        selected_tool,
                        user_confirmed=False,
                    )

                    if permission.decision == PermissionDecision.DENY:
                        tool_results = (
                            f"Tool permission denied: {permission.reason}"
                        )
                    elif permission.decision == PermissionDecision.CONFIRM:
                        tool_results = (
                            f"Tool requires confirmation: {permission.reason}"
                        )
                    else:
                        web_result = tool_registry.execute(
                            selected_tool,
                            tool_args,
                            tool_context,
                        )

                        collected = result_collector.collect(web_result)
                        verification = verify_tool_result(collected)

                        if verification.valid:
                            observation = tool_result_to_observation(web_result)
                            tool_results = observation
                        else:
                            if action in (ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH):
                                tool_results = (
                                    "Web search returned no results for this current "
                                    "information query. Do not fabricate current prices, "
                                    "rates, or values. Inform the user that current "
                                    "information could not be verified."
                                )
                            else:
                                tool_results = "Web search returned no results."

                            if web_result.error:
                                tool_results += f"\n\nSearch error: {web_result.error}"

        elif action == ACTION_PYTHON:
            print(f"[Agent Tool] Executing Python Code Interpreter...")

            # Check if user provided explicit Python code
            code_match = re.search(
                r"```(?:python)?\s*([\s\S]*?)```",
                message,
                re.IGNORECASE,
            )

            if code_match:
                code_to_run = code_match.group(1).strip()
            else:
                # Deterministic arithmetic extraction
                math_match = re.search(
                    r"(?:calculate|compute|solve|eval|what is)\s+([0-9+\-*/^().\s%]+)",
                    message,
                    re.IGNORECASE,
                )

                if math_match:
                    expr = math_match.group(1).strip().replace("^", "**")
                    code_to_run = f"print({expr})"
                else:
                    # Deterministic word-problem extraction
                    wp_expr = _extract_word_problem(message)

                    if wp_expr is not None:
                        code_to_run = f"print({wp_expr})"
                    else:
                        code_to_run = None

            # ============================================================
            # NO EXECUTABLE CODE FOUND
            # ============================================================
            if not code_to_run:
                tool_results = (
                    "Python code interpreter ready. "
                    "(No explicit executable snippet parsed)."
                )

            else:
                # ========================================================
                # PHASE 3.8.1
                # PYTHON TOOL ORCHESTRATION
                #
                # Select
                #   ↓
                # Validate
                #   ↓
                # Permission
                #   ↓
                # Execute
                #   ↓
                # Collect
                #   ↓
                # Verify
                #   ↓
                # Observe
                # ========================================================

                # --------------------------------------------------------
                # 1. TOOL SELECTION
                # --------------------------------------------------------
                selected_tool = select_tool(action)

                if selected_tool != "python_exec":
                    tool_results = (
                        "Tool selection mismatch: expected python_exec."
                    )

                    if not code_match:
                        direct_answer = tool_results

                else:
                    tool_args = {
                        "code": code_to_run,
                    }

                    # ----------------------------------------------------
                    # 2. TOOL VALIDATION
                    # ----------------------------------------------------
                    valid, validation_error = validate_tool_request(
                        tool_registry,
                        selected_tool,
                        tool_args,
                    )

                    if not valid:
                        tool_results = (
                            f"Tool validation failed: {validation_error}"
                        )

                        if not code_match:
                            direct_answer = tool_results

                    else:
                        # ------------------------------------------------
                        # 3. TOOL PERMISSION
                        # ------------------------------------------------
                        permission = evaluate_tool_permission(
                            tool_registry,
                            selected_tool,
                            user_confirmed=False,
                        )

                        if permission.decision == PermissionDecision.DENY:
                            tool_results = (
                                f"Tool permission denied: "
                                f"{permission.reason}"
                            )

                            if not code_match:
                                direct_answer = tool_results

                        elif permission.decision == PermissionDecision.CONFIRM:
                            tool_results = (
                                f"Tool requires confirmation: "
                                f"{permission.reason}"
                            )

                            if not code_match:
                                direct_answer = tool_results

                        else:
                            # --------------------------------------------
                            # 4. TOOL EXECUTION
                            # --------------------------------------------
                            python_result = tool_registry.execute(
                                selected_tool,
                                tool_args,
                                tool_context,
                            )

                            # --------------------------------------------
                            # 5. RESULT COLLECTION
                            # --------------------------------------------
                            collected = result_collector.collect(
                                python_result
                            )

                            # --------------------------------------------
                            # 6. RESULT VERIFICATION
                            # --------------------------------------------
                            verification = verify_tool_result(
                                collected
                            )

                            # --------------------------------------------
                            # 7. OBSERVATION FORMATTING
                            # --------------------------------------------
                            observation = tool_result_to_observation(
                                python_result
                            )

                            if verification.valid:
                                tool_results = observation

                                # Calculations and word problems:
                                # return deterministic result directly.
                                #
                                # Explicit Python code:
                                # let the LLM formulate the final answer.
                                if not code_match:
                                    direct_answer = (
                                        python_result.output
                                        or python_result.observation
                                    )

                            else:
                                tool_results = (
                                    f"Tool verification failed: "
                                    f"{verification.reason}"
                                )

                                if observation:
                                    tool_results += (
                                        f"\n\n{observation}"
                                    )

                                if not code_match:
                                    direct_answer = (
                                        python_result.error
                                        or python_result.output
                                        or verification.reason
                                    )



        elif action == ACTION_TIME:

            time_result = tool_registry.execute(

                "get_current_time",

                {},

                tool_context,

            )



            observation = tool_result_to_observation(time_result)



            if time_result.success:

                current_clock = time_result.output or time_result.observation

                tool_results = observation

                direct_answer = current_clock

            else:

                tool_results = observation



        elif action in (ACTION_RAG, ACTION_CODE_EXPLANATION):

            # Context is already fetched from search_pdf above.

            if rag_unavailable:

                tool_results = "Document retrieval is unavailable because the backend document dependencies are not installed."

            elif context:

                tool_results = "Document context retrieved from uploaded files — answer based on the document content above."

            else:

                # No relevant uploaded-file context was found. Fall back to chat.

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

                tool_results = (

                    "CODE EXPLANATION REQUEST:\n"

                    "Explain code from conversation history.\n"

                    "Requirements:\n"

                    "- Reference the actual code from previous messages\n"

                    "- Explain line by line or section by section as requested\n"

                    "- Do NOT generate new unrelated code\n"

                )



        # 5. Assemble Structured Context Prompt

        if perf_context is not None:

            perf_context.retrieval_ms += (time.perf_counter() - retrieval_started) * 1000

            prompt_started = time.perf_counter()

        prompt = build_prompt(

            question=message,

            history=history,

            memories=memories,

            context=context,

            tool_results=tool_results

        )

        if perf_context is not None:

            perf_context.prompt_build_ms = (time.perf_counter() - prompt_started) * 1000



        return {

            "prompt": prompt,

            "history": history,

            "context": context,

            "memories": memories,

            "action": action,

            "tool_results": tool_results,

            "answer": direct_answer,

        }
