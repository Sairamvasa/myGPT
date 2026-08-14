import re
from agents.memory_extractor import extract_memories
from agents.memory_search import search_memories
from agents.prompt_builder import build_prompt
from agents.tools import web_search, execute_python, get_current_time
from agents.planner import decide

from database import save_memory, get_history
from rag import search_pdf


class Agent:
    """
    MyGPT Autonomous Agent Core.
    Orchestrates Memory, RAG, Web Search, Code Interpreter, and LLM reasoning.
    """

    def run(self, message: str, chat_id=None):
        # 1. Decide action / tools needed
        action = decide(message)
        tool_results = None

        # 2. Extract and Persist Long-Term User Facts & Preferences
        facts = extract_memories(message)
        for fact in facts:
            save_memory(fact)

        if facts:
            print(f"[Memory] Saved {len(facts)} user fact(s): {facts}")

        # 3. Retrieve Contexts
        history = get_history(chat_id) if chat_id is not None else []
        memories = search_memories(message)
        context = search_pdf(message)

        # 4. Execute Autonomous Tools Based on Intent
        if action == "web":
            print(f"[Agent Tool] Executing Web Search for: {message}")
            results = web_search(message, max_results=5)
            if results:
                web_text = "\n\n".join([
                    f"**{item['title']}**\n{item['body']}\nSource: {item['link']}"
                    for item in results
                ])
                tool_results = f"Web Search Results:\n{web_text}"
            else:
                tool_results = "Web search returned no results."

        elif action == "python":
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
                    code_to_run = None

            if code_to_run:
                exec_output = execute_python(code_to_run)
                tool_results = f"Executed Python Code:\n```python\n{code_to_run}\n```\n\nOutput / Result:\n{exec_output}"
            else:
                tool_results = "Python code interpreter ready. (No explicit executable snippet parsed)."

        elif action == "time":
            current_clock = get_current_time()
            tool_results = f"System Real-Time Clock: {current_clock}"

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
            "tool_results": tool_results
        }