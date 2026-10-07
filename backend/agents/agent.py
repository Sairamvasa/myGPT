import logging
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

from agents.memory import extract_and_store_memories
from agents.memory_search import search_memories

from agents.prompt_builder import build_prompt

from agents.tools import web_search, execute_python, get_current_time

from agents.planner import decide, ACTION_CHAT, ACTION_PYTHON, ACTION_TIME, ACTION_WEB, ACTION_RAG, ACTION_VISION, ACTION_IMAGE_GEN, ACTION_MEMORY, ACTION_CODE, ACTION_CODE_EXPLANATION, ACTION_CURRENT_INFO, ACTION_WEB_RESEARCH, ACTION_GENERAL_KNOWLEDGE, ACTION_MATH, ACTION_CREATIVE

from agents.sequence_detector import extract_sequence_from_message, detect_sequence_pattern, get_sequence_answer

from agents.execution_loop import AgentExecutor, ResourceLimits

from backend.agents.memory_extractor import extract_memories
from database import save_memory, get_history

logger = logging.getLogger("MyGPT.Agent")


_executor = AgentExecutor(
    get_tool_registry(),
    limits=ResourceLimits(
        max_iterations=5,
        max_tool_calls=10,
        max_total_output_chars=256_000,
        max_execution_seconds=120,
        max_retries=2,
    ),
)


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
        history = []
        memories = []
        context = None
        tool_results = None
        direct_answer = None
        action = "chat"

        try:
            tool_registry = get_tool_registry()
            tool_context = ToolContext(
                user_id=user_id,
                chat_id=chat_id,
                project_id=project_id,
            )
            result_collector = ResultCollector()

            action = decide(message)

            if perf_context is not None:
                perf_context.routing_ms = (time.perf_counter() - started) * 1000

            # 2. Extract and Persist Long-Term User Facts & Preferences
            if action not in (ACTION_MATH, ACTION_GENERAL_KNOWLEDGE) and _PERSONAL_MARKERS.search(message) and user_id is not None:
                try:
                    if action in (ACTION_MEMORY,):
                        stored = extract_and_store_memories(
                            message,
                            user_id=user_id,
                        )
                        if stored:
                            logger.info(
                                "Memory extraction stored %d fact(s) for user_id=%s",
                                len(stored),
                                user_id,
                            )
                except Exception:
                    logger.exception(
                        "Memory extraction failed for user_id=%s action=%s",
                        user_id,
                        action,
                    )

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

            retrieval_started = time.perf_counter()
            try:
                history = get_history(chat_id) if chat_id is not None else []
            except Exception:
                logger.exception("History retrieval failed for chat_id=%s", chat_id)
                history = []

            if history and history[-1] == ("user", message):
                history = history[:-1]

            memories = []
            try:
                if user_id is not None and action in (ACTION_MEMORY, ACTION_WEB_RESEARCH):
                    memories = search_memories(message, user_id, action=action)
            except Exception:
                logger.exception("Memory search failed for user_id=%s action=%s", user_id, action)
                memories = []

            rag_unavailable = False
            contextual_followup = bool(
                re.search(
                    r"\b(?:what|how|why|where|which|does|is|are|explain|describe)\b.*\b(?:this|that|it|here|there|output|result|return|returns|value|function|code|script|file)\b",
                    message,
                    re.IGNORECASE,
                )
            )

            if (
                action == ACTION_CODE_EXPLANATION
                or (contextual_followup and action != ACTION_RAG)
            ) and user_id is not None:
                try:
                    from rag import search_pdf
                except ImportError:
                    search_pdf = None

                if project_id is not None:
                    try:
                        from rag import search_project_pdf
                        context = search_project_pdf(message, project_id)
                    except Exception:
                        logger.exception(
                            "Project RAG retrieval failed for project_id=%s user_id=%s",
                            project_id,
                            user_id,
                        )
                        context = None
                elif search_pdf is not None:
                    try:
                        context = search_pdf(message, user_id)
                    except Exception:
                        logger.exception(
                            "User RAG retrieval failed for user_id=%s",
                            user_id,
                        )
                        context = None
                else:
                    rag_unavailable = True

                if context:
                    history = []
                if context:
                    memories = []
                    if action in (ACTION_CHAT, ACTION_GENERAL_KNOWLEDGE, ACTION_CREATIVE):
                        action = ACTION_RAG

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

            if action in (ACTION_CODE, ACTION_CODE_EXPLANATION):
                if action == ACTION_CODE:
                    tool_results = (
                        "CODE GENERATION\n"
                        "Tool: code_generation\n"
                        "Status: success\n\n"
                        "Observation:\n"
                        "Code generation requested. The generated code will be produced by the LLM."
                    )
                    context = None
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
            else:
                outcome = _executor.execute(
                    message,
                    user_id=user_id,
                    chat_id=chat_id,
                    project_id=project_id,
                )
                tool_results = outcome.tool_results
                direct_answer = outcome.answer
                action = outcome.final_action or action

                if action == ACTION_RAG and outcome.steps:
                    last_step = outcome.steps[-1]
                    if last_step.result and last_step.result.success and last_step.result.output:
                        context = last_step.result.output
                        history = []
                        memories = []
                    elif last_step.result and last_step.result.success and not last_step.result.output:
                        context = None
                        action = ACTION_CHAT
                    elif not last_step.verified and last_step.error:
                        if tool_results:
                            tool_results += f"\n\nVerification: {last_step.error}"

                if outcome.error and not tool_results:
                    tool_results = outcome.error

            if perf_context is not None:
                perf_context.retrieval_ms += (time.perf_counter() - retrieval_started) * 1000
                prompt_started = time.perf_counter()

            prompt = build_prompt(
                question=message,
                history=history,
                memories=memories,
                context=context,
                tool_results=tool_results,
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
        except Exception:
            logger.exception(
                "Agent execution failed for user_id=%s chat_id=%s action=%s",
                user_id,
                chat_id,
                action,
            )
            return {
                "prompt": message,
                "history": history,
                "context": None,
                "memories": memories,
                "action": "error",
                "tool_results": "[AGENT_ERROR] A request processing error occurred. Please try again.",
                "answer": None,
            }
