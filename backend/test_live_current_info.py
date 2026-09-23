import requests
import json
import uuid
import sys

# Force UTF-8 output
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Create a unique user
unique_id = uuid.uuid4().hex[:8]
email = f"test_{unique_id}@example.com"
password = "testpassword123"

# Register
register_data = {'name': 'Test User', 'email': email, 'password': password}
r = requests.post('http://localhost:8001/register', json=register_data)
print('Register:', r.status_code, r.json())

# Login
login_data = {'email': email, 'password': password}
r = requests.post('http://localhost:8001/login', json=login_data)
print('Login:', r.status_code, r.json())
if r.status_code == 200 and r.json().get('success'):
    token = r.json()['access_token']
    print('Token:', token[:20] + '...')
else:
    print('Login failed')
    exit(1)

# Create chat
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
    r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id})
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        action = data.get("action", "unknown")
        answer = data.get("answer", "")
        print(f'Action: {action}')
        print(f'Answer: {answer[:500]}')
    else:
        print(f'Error: {r.text}')