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
token = requests.post('http://localhost:8001/login', json={'email': email, 'password': password}).json()['access_token']

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
r = requests.post('http://localhost:8001/new-chat', headers=headers)
chat_id = r.json()['chat_id']

# Test code generation - should use Gemini if available
q = "Write a Java program to calculate GCD of two numbers 48 and 18"
r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Action: {data.get("action", "unknown")}')
    print(f'Answer: {data.get("answer", "")[:800]}')
else:
    print(f'Error: {r.text}')

# Also test generate-image
r = requests.post('http://localhost:8001/generate-image', headers=headers, data={'prompt': 'a cat', 'aspect_ratio': '1:1'}, timeout=60)
print(f'\nGenerate-image Status: {r.status_code}')
print(f'Generate-image Response: {r.text[:500]}')