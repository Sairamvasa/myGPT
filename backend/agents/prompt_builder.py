from datetime import datetime
from agents.prompts import SYSTEM_PROMPT


def build_prompt(question: str, history=None, memories=None, context=None, tool_results=None):
    """
    Build a comprehensive, structured prompt for Gemini including System instructions,
    long-term memory, conversation history, document/tool context, and user question.
    """
    now = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")

    sections = [
        SYSTEM_PROMPT,
        f"\n**Environment Metadata**:\n- Current Date & Time: {now}\n"
    ]

    # Long-Term Memories
    if memories:
        memory_lines = "\n".join([f"- {mem}" for mem in memories])
        sections.append(f"### 🧠 Long-Term User Memory\n{memory_lines}\n")

    # Conversation History
    if history:
        history_text = ""
        for role, message in history:
            role_label = "User" if role == "user" else "Assistant"
            history_text += f"**{role_label}**: {message}\n\n"
        sections.append(f"### 💬 Recent Conversation History\n{history_text.strip()}\n")

    # Document Context (RAG)
    if context:
        sections.append(f"### 📄 Document & Knowledge Context\n{context}\n")

    # Dynamic Tool Outputs (e.g. Python code execution, web search results, time)
    if tool_results:
        sections.append(f"### ⚙️ Autonomous Tool Observations\n{tool_results}\n")

    # Current User Question
    sections.append(f"### 👤 Current User Request\n{question}\n\nPlease provide a helpful, intelligent, and beautifully formatted response.")

    return "\n\n---\n\n".join(sections)