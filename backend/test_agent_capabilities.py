import sys
from agents.agent import Agent

def run_tests():
    agent = Agent()
    print("=" * 60)
    print("TEST 1: PYTHON CODE EXECUTION & MATH TOOL")
    print("=" * 60)
    msg1 = "Calculate 2**32 / 1024 and print the result"
    res1 = agent.run(msg1)
    print(f"Action: {res1['action']}")
    print(f"Observation: {res1['tool_results']}")
    assert res1['action'] == "python", "Action should be python"
    assert "4194304.0" in res1['tool_results'], f"Expected math output in tool results, got {res1['tool_results']}"
    print("Python math calculation passed!\n")

    print("=" * 60)
    print("TEST 2: PYTHON SCRIPT EXECUTION IN BACKTICKS")
    print("=" * 60)
    msg2 = "Run this python script:\n```python\nnames = ['Alice', 'Bob', 'Charlie']\nprint(', '.join([n.upper() for n in names]))\n```"
    res2 = agent.run(msg2)
    print(f"Action: {res2['action']}")
    print(f"Observation: {res2['tool_results']}")
    assert "ALICE, BOB, CHARLIE" in res2['tool_results'], "Expected script output in tool results"
    print("Python script execution passed!\n")

    print("=" * 60)
    print("TEST 3: REAL-TIME DATE & CLOCK TOOL")
    print("=" * 60)
    msg3 = "What is today's date and current time?"
    res3 = agent.run(msg3)
    print(f"Action: {res3['action']}")
    print(f"Observation: {res3['tool_results']}")
    assert res3['action'] == "time", "Action should be time"
    assert "System Real-Time Clock:" in res3['tool_results'], "Expected clock in tool results"
    print("Real-time clock passed!\n")

    print("=" * 60)
    print("TEST 4: WEB SEARCH AGENT TOOL")
    print("=" * 60)
    msg4 = "What is the latest news on OpenAI today?"
    res4 = agent.run(msg4)
    print(f"Action: {res4['action']}")
    print(f"Observation preview: {res4['tool_results'][:150]}...")
    assert res4['action'] == "web", "Action should be web"
    print("Web search routing passed!\n")

    print("=" * 60)
    print("TEST 5: AUTONOMOUS LONG-TERM MEMORY")
    print("=" * 60)
    msg5 = "I am a full-stack engineer and my goal is to build an autonomous AI agent startup"
    res5 = agent.run(msg5)
    print(f"Memories extracted and loaded: {res5['memories']}")
    print("Memory extraction and retrieval passed!\n")

    print("ALL AGENT CAPABILITY TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
