from datetime import datetime


def build_prompt(question, history=None, memories=None, context=None):

    now = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")

    prompt = f"""
You are MyGPT, an intelligent AI assistant.

Rules:
- Use LONG TERM MEMORY whenever it is relevant.
- Use CHAT HISTORY to continue the conversation naturally.
- Use DOCUMENT CONTEXT only when relevant.
- If the answer is in memory, prefer memory over guessing.
- Never contradict saved memories.
- If you don't know something, say you don't know.

Current Date & Time:
{now}
"""

    # Long-Term Memory
    if memories:
        prompt += "\n\nLONG TERM MEMORY\n----------------\n"
        for memory in memories:
            prompt += f"- {memory}\n"

    # Chat History
    if history:
        prompt += "\n\nCHAT HISTORY\n------------\n"
        for role, message in history:
            if role == "user":
                prompt += f"User: {message}\n"
            else:
                prompt += f"Assistant: {message}\n"

    # PDF Context
    if context:
        prompt += f"""

DOCUMENT CONTEXT
----------------
{context}
"""

    # Current Question
    prompt += f"""

USER QUESTION
-------------
{question}

Answer naturally using the available context.
"""

    return prompt