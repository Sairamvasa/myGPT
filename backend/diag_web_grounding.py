"""Trace the actual web search flow for the France capital question."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from agents.tools import web_search
from agents.planner import decide
from agents.prompt_builder import build_prompt
from agents.prompts import SYSTEM_PROMPT

# 1. Planner routing
msg = "What is the capital of France in Asia?"
action = decide(msg)
print("1. PLANNER ROUTING")
print(f"   Question: {msg!r}")
print(f"   Action: {action}")
print()

# 2. Web search
print("2. WEB SEARCH")
print(f"   Query sent to web_search(): {msg!r}")
print(f"   max_results=3")
results = web_search(msg, max_results=3)
print(f"   Results returned: {len(results)}")
for i, r in enumerate(results, 1):
    print(f"   --- Result {i} ---")
    print(f"   Title: {r['title']}")
    print(f"   Body: {r['body'][:300]}")
    print(f"   Link: {r['link']}")
print()

# 3. Tool results formatting (exact agent.py code)
print("3. TOOL RESULTS FORMATTING")
if results:
    web_text = "\n\n".join([
        f"**{item['title']}**\n{item['body']}\nSource: {item['link']}"
        for item in results
    ])
    tool_results = f"Web Search Results:\n{web_text}"
else:
    tool_results = "Web search returned no results."

print(f"   Exact tool_results string ({len(tool_results)} chars):")
print(f"   {tool_results[:800]}")
print()

# 4. Check if results identify France as in Europe
print("4. RESULT QUALITY ANALYSIS")
europe_mentions = sum(1 for r in results if "europe" in r["body"].lower() or "europe" in r["title"].lower())
paris_mentions = sum(1 for r in results if "paris" in r["body"].lower() or "paris" in r["title"].lower())
asia_mentions = sum(1 for r in results if "asia" in r["body"].lower() or "asia" in r["title"].lower())
print(f"   Results mentioning 'Europe': {europe_mentions}/{len(results)}")
print(f"   Results mentioning 'Paris': {paris_mentions}/{len(results)}")
print(f"   Results mentioning 'Asia': {asia_mentions}/{len(results)}")
print()

# 5. Build the exact prompt
print("5. EXACT PROMPT SENT TO OLLAMA")
prompt = build_prompt(
    question=msg,
    history=[],
    memories=[],
    context=None,
    tool_results=tool_results,
)
print(f"   Prompt length: {len(prompt)} chars")
print(f"   Contains 'Web Search Results': {'Web Search Results' in prompt}")
print(f"   Contains 'Paris': {'Paris' in prompt}")
print(f"   Contains 'Europe': {'Europe' in prompt}")
print(f"   Contains 'Bandar Seri Begawan': {'Bandar Seri Begawan' in prompt}")
print()

# 6. Check system prompt for false-premise correction
print("6. SYSTEM PROMPT ANALYSIS")
checks = [
    ("false premise", "false premise" in SYSTEM_PROMPT.lower()),
    ("correct the user", "correct the user" in SYSTEM_PROMPT.lower()),
    ("contradiction", "contradiction" in SYSTEM_PROMPT.lower()),
    ("prioritize retrieved context", "prioritize the retrieved context" in SYSTEM_PROMPT.lower()),
    ("conflicts with training data", "conflicts with your training data" in SYSTEM_PROMPT.lower()),
]
for label, found in checks:
    print(f"   '{label}': {found}")

print()
print("7. ROOT CAUSE CLASSIFICATION")
print("   A. search query problem")
print("   B. search-result quality problem")
print("   C. prompt-grounding problem")
print("   D. LLM interpretation problem")
print("   E. combination")