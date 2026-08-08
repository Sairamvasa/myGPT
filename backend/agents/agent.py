from typer import prompt

from agents.memory_extractor import extract_memories
from agents.memory_search import search_memories
from agents.prompt_builder import build_prompt
from agents.tools import web_search
from agents.planner import decide

from database import save_memory, get_history
from rag import search_pdf
from gemini import ask_gemini


class Agent:

    def run(self, message, chat_id):

        # Decide which tool to use
        action = decide(message)

        # Save Long-Term Memory
        facts = extract_memories(message)

        for fact in facts:
            save_memory(fact)

        if facts:
            print("Saved Memories:", facts)

        # Load Chat History
        history = get_history(chat_id)

        # Load Relevant Memories
        memories = search_memories(message)

        # Load PDF Context
        context = search_pdf(message)

        # Optional Web Search
        if action == "web":

            results = web_search(message)

            web_context = ""

            for item in results:
                web_context += (
                    f"Title: {item['title']}\n"
                    f"Content: {item['body']}\n"
                    f"Source: {item['link']}\n\n"
                )

            if context:
                context += "\n\n" + web_context
            else:
                context = web_context

        # Build Prompt
        prompt = build_prompt(
    question=message,
    history=history,
    memories=memories,
    context=context
)

        return {
            "prompt": prompt,
            "history": history,
            "context": context,
            "memories": memories
}