import sys
import io
import os
from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("GEMINI_API_KEY:", os.getenv("GEMINI_API_KEY")[:20] if os.getenv("GEMINI_API_KEY") else "NOT SET")

from agents.agent import Agent
from llm import ask_gemini, _get_gemini_client, GEMINI_API_KEY as GEMINI_API_KEY_MODULE
from perf_telemetry import create_context

print("Module GEMINI_API_KEY:", GEMINI_API_KEY_MODULE[:20] if GEMINI_API_KEY_MODULE else "NOT SET")

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