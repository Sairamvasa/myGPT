import requests

url = "http://127.0.0.1:8000/register"
res = requests.post(url, json={"name": "test2", "email": "test2@test.com", "password": "password123"})
print(res.status_code, res.text)

if res.status_code in [200, 409]:
    url = "http://127.0.0.1:8000/login"
    res = requests.post(url, json={"email": "test2@test.com", "password": "password123"})
    token = res.json().get("access_token")
    print("Token:", token)

    url = "http://127.0.0.1:8000/vision"
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": open("test_image.jpg", "rb")}
    data = {"prompt": "What is this?"}
    res = requests.post(url, headers=headers, files=files, data=data)
    print("Vision:", res.status_code, res.text)
