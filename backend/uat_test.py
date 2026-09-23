import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
import app as app_module

client = TestClient(app_module.app)

# Create two users
print('=== SETUP: CREATE USERS ===')
for i, email in enumerate(['uat1@example.com', 'uat2@example.com']):
    client.post('/register', json={'name': f'UAT User {i+1}', 'email': email, 'password': 'password123'})
    resp = client.post('/login', json={'email': email, 'password': 'password123'})
    token = resp.json().get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/new-chat', headers=headers)
    chat_id = resp.json().get('chat_id')
    if i == 0:
        token1, headers1, chat_id1 = token, headers, chat_id
    else:
        token2, headers2, chat_id2 = token, headers, chat_id
    print(f'  User {i+1}: chat_id={chat_id}')

# 1. NORMAL CHAT
print('\n=== 1. NORMAL CHAT ===')
for msg in ['What is Python?', 'Explain machine learning simply.']:
    resp = client.post('/chat', headers=headers1, json={'message': msg, 'chat_id': chat_id1})
    answer = resp.json().get('answer', '')
    print(f'  Q: {msg}')
    print(f'  A: {answer[:100]}...')
    print(f'  Status: {resp.status_code}')

# 2. CURRENT INFORMATION
print('\n=== 2. CURRENT INFORMATION ===')
for msg in [
    "Today's petrol price in Hyderabad",
    'Current Bitcoin price',
    "Today's weather in Hyderabad",
    'Latest AI news'
]:
    resp = client.post('/chat', headers=headers1, json={'message': msg, 'chat_id': chat_id1})
    answer = resp.json().get('answer', '')
    print(f'  Q: {msg}')
    print(f'  A: {answer[:150]}...')
    print(f'  Status: {resp.status_code}')

# 3. CODE GENERATION
print('\n=== 3. CODE GENERATION ===')
resp = client.post('/new-chat', headers=headers1)
code_chat_id = resp.json().get('chat_id')
for i, msg in enumerate([
    'Write a Java program to calculate GCD of 48 and 18',
    'Explain this code line by line',
    'Optimize it',
    'Convert it to Python',
    'Add comments'
]):
    resp = client.post('/chat', headers=headers1, json={'message': msg, 'chat_id': code_chat_id})
    answer = resp.json().get('answer', '')
    print(f'  Step {i+1}: {msg[:50]}')
    print(f'  A: {answer[:150]}...')
    print(f'  Status: {resp.status_code}')

# 4. CODE EXECUTION
print('\n=== 4. CODE EXECUTION ===')
resp = client.post('/chat', headers=headers1, json={
    'message': 'What is the output of:\nprint(10 + 20)',
    'chat_id': chat_id1
})
answer = resp.json().get('answer', '')
print(f'  Q: What is the output of print(10 + 20)')
print(f'  A: {answer[:150]}...')
print(f'  Status: {resp.status_code}')

# 5. RAG
print('\n=== 5. RAG ===')
with open('test_project.txt', 'w') as f:
    f.write('PROJECT_OWNER = ORBITAL_FALCON_92841\n')

with open('test_project.txt', 'rb') as f:
    files = {'files': ('test_project.txt', f, 'text/plain')}
    resp = client.post('/upload-files', headers=headers1, files=files)
print('Upload:', resp.status_code, resp.json())

resp = client.post('/chat', headers=headers1, json={'message': 'Who is the project owner?', 'chat_id': chat_id1})
answer = resp.json().get('answer', '')
print(f'  Q: Who is the project owner?')
print(f'  A: {answer[:150]}...')
print(f'  Status: {resp.status_code}')

# 6. MEMORY
print('\n=== 6. MEMORY ===')
resp = client.post('/chat', headers=headers1, json={'message': 'My name is Rahul.', 'chat_id': chat_id1})
print('Set name:', resp.status_code)
resp = client.post('/chat', headers=headers1, json={'message': 'What is my name?', 'chat_id': chat_id1})
answer = resp.json().get('answer', '')
print(f'  Q: What is my name?')
print(f'  A: {answer}')
print(f'  Status: {resp.status_code}')

# 7. SECURITY - Cross-user isolation
print('\n=== 7. SECURITY (Cross-user isolation) ===')

# User 2 tries to access User 1's chat
resp = client.post('/chat', headers=headers2, json={'message': 'Hello', 'chat_id': chat_id1})
print(f'User 2 access User 1 chat: {resp.status_code} (expected 403/404)')

# User 2 tries to list User 1's conversations
resp = client.get('/conversations', headers=headers2)
print(f'User 2 conversations: {resp.status_code}, count={len(resp.json()) if resp.status_code==200 else "N/A"}')

# User 2 tries to access RAG
resp = client.post('/chat', headers=headers2, json={'message': 'Who is the project owner?', 'chat_id': chat_id2})
answer = resp.json().get('answer', '')
print(f'User 2 RAG query: {answer[:100]}...')

# User 2 tries to access User 1's memory
resp = client.post('/chat', headers=headers2, json={'message': 'What is my name?', 'chat_id': chat_id2})
answer = resp.json().get('answer', '')
print(f'User 2 memory query: {answer[:100]}...')

# 8. STREAMING
print('\n=== 8. STREAMING ===')
resp = client.post('/stream', headers=headers1, json={'message': 'Write a long explanation of how neural networks work', 'chat_id': chat_id1})
print(f'Stream status: {resp.status_code}')
if resp.status_code == 200:
    content = ''
    for chunk in resp.iter_bytes():
        content += chunk.decode('utf-8', errors='ignore')
        if len(content) > 200:
            break
    print(f'First 200 chars: {content[:200]}...')

print('\n=== UAT BACKEND TESTS COMPLETE ===')