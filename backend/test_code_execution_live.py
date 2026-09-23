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

# Test code execution
print('\n=== Code Execution Tests ===')

# Java GCD
q = "Write a Java program to calculate GCD of two numbers 48 and 18"
r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
print(f'Query: {q}')
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Action: {data.get("action", "unknown")}')
    print(f'Answer: {data.get("answer", "")[:800]}')

# Java Prime
q = "Write a Java program to check if 17 is prime, then check if 20 is prime"
r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
print(f'\nQuery: {q}')
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Action: {data.get("action", "unknown")}')
    print(f'Answer: {data.get("answer", "")[:800]}')

# Python sort
q = "Write Python code to sort the list [5, 2, 8, 1]"
r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
print(f'\nQuery: {q}')
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Action: {data.get("action", "unknown")}')
    print(f'Answer: {data.get("answer", "")[:800]}')