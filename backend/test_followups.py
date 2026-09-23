import sys
import io
import os
from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from agents.agent import Agent
from llm import ask_llm_routed
from perf_telemetry import create_context

agent = Agent()

# Use the chat_id that has the GCD code
chat_id = 231

# Test follow-up: Explain this code
print("=== Follow-up: Explain this code ===")
result = agent.run('Explain this code line by line.', chat_id=chat_id, user_id=1)
print('Follow-up action:', result.get('action'))
print('History length:', len(result.get('history', [])))
if result.get('history'):
    print('Last history:', result['history'][-1])

perf = create_context('test', 'llama3.2:1b')
try:
    ans = ask_llm_routed(result['prompt'], 'chat', perf_context=perf)
    print('Answer:', ans[:1500])
except Exception as e:
    print('Error:', type(e).__name__, str(e))

# Test follow-up: Optimize this code
print("\n=== Follow-up: Optimize this code ===")
result2 = agent.run('Optimize this code.', chat_id=chat_id, user_id=1)
print('Follow-up action:', result2.get('action'))

perf2 = create_context('test', 'llama3.2:1b')
try:
    ans2 = ask_llm_routed(result2['prompt'], 'chat', perf_context=perf2)
    print('Answer:', ans2[:1500])
except Exception as e:
    print('Error:', type(e).__name__, str(e))

# Test follow-up: Convert to Python
print("\n=== Follow-up: Convert to Python ===")
result3 = agent.run('Convert it to Python.', chat_id=chat_id, user_id=1)
print('Follow-up action:', result3.get('action'))

perf3 = create_context('test', 'llama3.2:1b')
try:
    ans3 = ask_llm_routed(result3['prompt'], 'chat', perf_context=perf3)
    print('Answer:', ans3[:1500])
except Exception as e:
    print('Error:', type(e).__name__, str(e))

# Test follow-up: Add comments
print("\n=== Follow-up: Add comments ===")
result4 = agent.run('Add comments.', chat_id=chat_id, user_id=1)
print('Follow-up action:', result4.get('action'))

perf4 = create_context('test', 'llama3.2:1b')
try:
    ans4 = ask_llm_routed(result4['prompt'], 'chat', perf_context=perf4)
    print('Answer:', ans4[:1500])
except Exception as e:
    print('Error:', type(e).__name__, str(e))