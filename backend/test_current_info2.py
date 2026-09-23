import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agents.agent import Agent
from llm import ask_gemini
from perf_telemetry import create_context

agent = Agent()
result = agent.run("Today's petrol price in Hyderabad", chat_id=1, user_id=1)
print("Action:", result.get("action"))
print("Tool results:", result.get("tool_results", "")[:500])

# Test ask_gemini directly
perf = create_context("test", "gemini-1.5-flash")
try:
    answer = ask_gemini(result["prompt"], perf_context=perf, action="current_info")
    print("Gemini answer:", answer)
except Exception as e:
    print("Gemini Error:", type(e).__name__, str(e))