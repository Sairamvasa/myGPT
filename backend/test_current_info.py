import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agents.agent import Agent
from llm import ask_llm_routed
from perf_telemetry import create_context

agent = Agent()
result = agent.run("Today's petrol price in Hyderabad", chat_id=1, user_id=1)
print("Action:", result.get("action"))

perf = create_context("test", "gemini-1.5-flash")
try:
    answer = ask_llm_routed(result["prompt"], "current_info", perf_context=perf)
    print("Full answer:", answer)
except Exception as e:
    print("Error:", type(e).__name__, str(e))

print("\n--- Bitcoin test ---")
result2 = agent.run("Current Bitcoin price", chat_id=1, user_id=1)
print("Action:", result2.get("action"))

perf2 = create_context("test", "gemini-1.5-flash")
try:
    answer2 = ask_llm_routed(result2["prompt"], "current_info", perf_context=perf2)
    print("Full answer:", answer2)
except Exception as e:
    print("Error:", type(e).__name__, str(e))