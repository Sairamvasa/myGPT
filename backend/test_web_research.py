import requests
import uuid
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

unique_id = uuid.uuid4().hex[:8]
email = f"test_{unique_id}@example.com"
password = "testpassword123"

r = requests.post('http://localhost:8001/register', json={'name': 'Test User', 'email': email, 'password': password})
token = requests.post('http://localhost:8001/login', json={'email': email, 'password': password}).json()['access_token']

headers = {'Authorization': f'Bearer {token}'}

r = requests.post('http://localhost:8001/new-chat', headers=headers)
chat_id = r.json()['chat_id']
print(f'Chat ID: {chat_id}')

# Test with a query that should route to Gemini (web_research)
r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': 'Latest AI news', 'chat_id': chat_id}, timeout=60)
print(f'Web research Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'Action: {data.get("action", "unknown")}')
    answer = data.get("answer", "")
    print(f'Answer: {answer[:500]}')
else:
    print(f'Response: {r.text}')