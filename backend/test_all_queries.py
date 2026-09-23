import requests
import uuid
import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

unique_id = uuid.uuid4().hex[:8]
email = f"test_{unique_id}@example.com"
password = "testpassword123"

r = requests.post('http://localhost:8001/register', json={'name': 'Test User', 'email': email, 'password': password})
print('Register:', r.status_code, r.json())

r = requests.post('http://localhost:8001/login', json={'email': email, 'password': password})
print('Login:', r.status_code, r.json())
token = r.json()['access_token']

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
r = requests.post('http://localhost:8001/new-chat', headers=headers)
print('New chat:', r.status_code, r.json())
chat_id = r.json()['chat_id']

# Test queries
queries = [
    "Today's petrol price in India",
    "Today's petrol price in Hyderabad",
    "Current Bitcoin price",
    "Today's weather in Hyderabad",
    "Latest AI news"
]

for q in queries:
    print(f'\n=== Query: {q} ===')
    r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        action = data.get("action", "unknown")
        answer = data.get("answer", "")
        print(f'Action: {action}')
        print(f'Answer: {answer[:500]}')
    else:
        print(f'Error: {r.text}')