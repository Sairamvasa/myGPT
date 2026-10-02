"""Test current-info query + direct LLM call (standalone integration script)."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent import Agent
from llm import ask_llm_routed
from perf_telemetry import create_context


def main():
    agent = Agent()
    result = agent.run("Today's petrol price in Hyderabad", chat_id=1, user_id=1)
    print("Action:", result.get("action"))
    print("Tool results:", result.get("tool_results", "")[:500])

    # Test ask_llm_routed directly
    perf = create_context("test", "gemini-1.5-flash")
    try:
        answer = ask_llm_routed(result["prompt"], "current_info", perf_context=perf)
        print("Answer:", answer)
    except Exception as e:
        print("Error:", type(e).__name__, str(e))


if __name__ == "__main__":
    main()
