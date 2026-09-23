import sys
sys.path.insert(0, 'backend')
from agents.agent import Agent

agent = Agent()
for msg in ['hi', 'hello', 'What is Python?']:
    result = agent.run(msg, chat_id=42, user_id=7)
    print(f'Message: {msg!r}')
    print(f'  Action: {result["action"]}')
    print(f'  Prompt: {repr(result["prompt"][:100])}')
    print()