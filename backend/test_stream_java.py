"""Streaming Java-codegen smoke test against a live MyGPT backend.
Standalone script — requires the backend running on http://localhost:8001.
Run directly with ``python test_stream_java.py``.
"""
import requests
import uuid


def main():
    unique_id = uuid.uuid4().hex[:8]
    email = f"test_{unique_id}@example.com"
    password = "testpassword123"

    r = requests.post('http://localhost:8001/register', json={'name': 'Test User', 'email': email, 'password': password})
    token = requests.post('http://localhost:8001/login', json={'email': email, 'password': password}).json()['access_token']

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    r = requests.post('http://localhost:8001/new-chat', headers=headers)
    chat_id = r.json()['chat_id']

    # Try Java query with stream endpoint
    q = "Write a Java program to calculate GCD of two numbers 48 and 18"
    r = requests.post('http://localhost:8001/stream', headers=headers, json={'message': q, 'chat_id': chat_id}, timeout=120)
    print(f'Status: {r.status_code}')
    print(f'Response length: {len(r.text)}')
    print(f'Response: {r.text[:1000]}')


if __name__ == "__main__":
    main()
