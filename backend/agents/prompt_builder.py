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
        sections.append(f"### 🧠 Long-Term User Memory\nUse these facts to personalize your response.\n{memory_lines}\n")
    else:
        sections.append("### 🧠 Long-Term User Memory\nNo long-term memories are available for this user. Do not invent personal details.\n")

    # Conversation History — capped to last 20 messages to stay within
    # Gemini's context window and keep the prompt focused.
    if history:
        recent_history = history[-20:]
        history_text = ""
        for role, message in recent_history:
            role_label = "User" if role == "user" else "Assistant"
            history_text += f"**{role_label}**: {message}\n\n"
        sections.append(f"### 💬 Recent Conversation History\nUse this to maintain continuity.\n{history_text.strip()}\n")
    else:
        sections.append("### 💬 Recent Conversation History\nNo conversation history is available for this chat. Do not invent past exchanges.\n")

    # Document Context (RAG)
    if context:
        sections.append(f"### 📄 Document & Knowledge Context\nUse this uploaded document context to answer accurately.\n{context}\n")
    else:
        sections.append("### 📄 Document & Knowledge Context\nNo documents were uploaded or retrieved for this request. Do not invent document content or citations.\n")

    # Dynamic Tool Outputs (e.g. Python code execution, web search results, time)
    if tool_results:
        sections.append(f"### 🛠️ Autonomous Tool Observations\nUse these tool results to inform your answer.\n{tool_results}\n")
    else:
        sections.append("### 🛠️ Autonomous Tool Observations\nNo tools were executed for this request. Do not invent tool results, command outputs, or search results.\n")

    # Current User Question
    sections.append(f"### 👤 Current User Request\n{question}")

    sections.append(
        "### 🔍 Final Quality Check\n"
        "Before providing your final answer, verify internally:\n"
        "1. Does this answer the user's actual question?\n"
        "2. Is it relevant and clear?\n"
        "3. Is it factually supported by the context provided?\n"
        "4. Is the formatting correct?\n"
        "5. Is code syntactically valid when included?\n"
        "6. Did I avoid inventing facts, citations, or tool/file usage?\n"
        "7. Did I avoid exposing private user data?\n"
        "8. Did I avoid contradicting retrieved source information without explanation?\n"
        "Provide only the final polished response. Do not narrate this verification process."
    )

    return "\n\n---\n\n".join(sections)