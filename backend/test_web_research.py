"""Live web-research smoke test against a running MyGPT backend.
Standalone script — requires the backend running on http://localhost:8001.
Run directly with ``python test_web_research.py``.
"""
import requests
import uuid


def main():
    unique_id = uuid.uuid4().hex[:8]
    email = f"test_{unique_id}@example.com"
    password = "testpassword123"

    r = requests.post('http://localhost:8001/register', json={'name': 'Test User', 'email': email, 'password': password})
    token = requests.post('http://localhost:8001/login', json={'email': email, 'password': password}).json()['access_token']

    headers = {'Authorization': f'Bearer {token}'}

    r = requests.post('http://localhost:8001/new-chat', headers=headers)
    chat_id = r.json()['chat_id']
    print(f'Chat ID: {chat_id}')

    # Test with a query that should route to web research
    r = requests.post('http://localhost:8001/chat', headers=headers, json={'message': 'Latest AI news', 'chat_id': chat_id}, timeout=60)
    print(f'Web research Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'Action: {data.get("action", "unknown")}')
        answer = data.get("answer", "")
        print(f'Answer: {answer[:500]}')
    else:
        print(f'Response: {r.text}')


if __name__ == "__main__":
    main()
