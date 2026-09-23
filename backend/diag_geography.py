"""Diagnose factual hallucination: geography questions with llama3.2:1b."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from llm import _get_client, _chat_messages, _generation_options, OLLAMA_MODEL, SYSTEM_PROMPT
from agents.prompt_builder import build_prompt
from agents.planner import decide

client = _get_client()

def ask(messages, np=160):
    resp = client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        stream=False,
        options={**_generation_options(), "num_predict": np},
    )
    return resp.get("message", {}).get("content", "").strip()

# 1. Planner routing
print("=" * 70)
print("1. PLANNER ROUTING")
print("=" * 70)
for q in [
    "What is the capital of Andhra Pradesh?",
    "What about Amaravati?",
    "Amaravati is a city in Karnataka",
]:
    print("  %r -> %s" % (q, decide(q)))

# 2. Bare question
print("\n" + "=" * 70)
print("2. BARE QUESTION (no system prompt, no history)")
print("=" * 70)
a = ask([{"role": "user", "content": "What is the capital of Andhra Pradesh?"}])
print("  Answer: %r" % a)

# 3. Plain chat prompt (production path)
print("\n" + "=" * 70)
print("3. PLAIN CHAT PROMPT (production path)")
print("=" * 70)
prompt = build_prompt(
    question="What is the capital of Andhra Pradesh?",
    history=[],
    memories=[],
    context=None,
    tool_results=None,
)
a = ask(_chat_messages(prompt))
print("  Answer: %r" % a)

# 4. With web search tool results injected
print("\n" + "=" * 70)
print("4. WITH WEB SEARCH TOOL RESULTS INJECTED")
print("=" * 70)
prompt4 = build_prompt(
    question="What is the capital of Andhra Pradesh?",
    history=[],
    memories=[],
    context=None,
    tool_results=(
        "Web Search Results:\n"
        "**Amaravati**\n"
        "Amaravati is the capital city of the Indian state of Andhra Pradesh.\n"
        "Source: https://en.wikipedia.org/wiki/Amaravati"
    ),
)
a = ask(_chat_messages(prompt4))
print("  Answer: %r" % a)

# 5. Follow-up with history
print("\n" + "=" * 70)
print("5. FOLLOW-UP 'What about Amaravati?' WITH HISTORY")
print("=" * 70)
prompt5 = build_prompt(
    question="What about Amaravati?",
    history=[
        ("user", "What is the capital of Andhra Pradesh?"),
        ("assistant", "The capital of Andhra Pradesh is Amaravati."),
    ],
    memories=[],
    context=None,
    tool_results=None,
)
a = ask(_chat_messages(prompt5))
print("  Answer: %r" % a)

# 6. Check system prompt for geographic instructions
print("\n" + "=" * 70)
print("6. SYSTEM PROMPT ANALYSIS")
print("=" * 70)
geo_keywords = ["capital", "geographic", "geography", "current", "real-time", "real time", "search", "web"]
for kw in geo_keywords:
    found = kw.lower() in SYSTEM_PROMPT.lower()
    print("  Contains '%s': %s" % (kw, found))

# 7. Check if web search is available
print("\n" + "=" * 70)
print("7. WEB SEARCH AVAILABILITY")
print("=" * 70)
try:
    from agents.tools import web_search
    results = web_search("capital of Andhra Pradesh", max_results=2)
    if results:
        for r in results:
            print("  Title: %s" % r['title'])
            print("  Body: %s" % r['body'][:200])
    else:
        print("  Web search returned no results")
except Exception as e:
    print("  Web search error: %s" % e)

print("\n" + "=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)