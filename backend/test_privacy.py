import os
import sys
import time
import tempfile

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from database import save_memory, get_all_memories
from rag import search_pdf

client = TestClient(app)
suffix = str(int(time.time()))
email_a = f"usera_{suffix}@test.com"
email_b = f"userb_{suffix}@test.com"

print("=" * 60)
print("MULTI-USER PRIVACY TESTS")
print("=" * 60)

# 1. Register two users
ra = client.post("/register", json={"name": "User A", "email": email_a, "password": "pass123"})
rb = client.post("/register", json={"name": "User B", "email": email_b, "password": "pass123"})
print("Register A:", ra.json())
print("Register B:", rb.json())

# 2. Login to get JWTs
la = client.post("/login", json={"email": email_a, "password": "pass123"})
lb = client.post("/login", json={"email": email_b, "password": "pass123"})
token_a = la.json()["access_token"]
token_b = lb.json()["access_token"]
user_a = la.json()["user_id"]
user_b = lb.json()["user_id"]
print(f"User A id={user_a}, User B id={user_b}")

ha = {"Authorization": f"Bearer {token_a}"}
hb = {"Authorization": f"Bearer {token_b}"}

# 3. Create a chat for each user
ca = client.post("/new-chat", headers=ha).json()
cb = client.post("/new-chat", headers=hb).json()
chat_a = ca["chat_id"]
chat_b = cb["chat_id"]
print(f"Chat A={chat_a}, Chat B={chat_b}")

# 4. Conversations isolation
conv_a = client.get("/conversations", headers=ha).json()
conv_b = client.get("/conversations", headers=hb).json()
ids_a = [c["chat_id"] for c in conv_a]
ids_b = [c["chat_id"] for c in conv_b]
print("A sees chats:", ids_a)
print("B sees chats:", ids_b)
assert chat_a in ids_a and chat_b not in ids_a, "FAIL: A sees B's chat"
assert chat_b in ids_b and chat_a not in ids_b, "FAIL: B sees A's chat"
print("PASS: conversations isolated")

# 5. Cross-user history access -> must be 403/404
r = client.get(f"/history/{chat_b}", headers=ha)
print("A accessing B's history:", r.status_code)
assert r.status_code in (403, 404), "FAIL: A could access B's history"
r = client.get(f"/history/{chat_a}", headers=hb)
print("B accessing A's history:", r.status_code)
assert r.status_code in (403, 404), "FAIL: B could access A's history"
r = client.get(f"/history/{chat_a}", headers=ha)
print("A accessing own history:", r.status_code)
assert r.status_code == 200, "FAIL: A cannot access own history"
print("PASS: history ownership enforced")

# 6. Cross-user chat post -> must be 403/404
r = client.post("/chat", headers=ha, json={"message": "hi", "chat_id": chat_b})
print("A posting to B's chat:", r.status_code)
assert r.status_code in (403, 404), "FAIL: A could post to B's chat"
print("PASS: chat ownership enforced")

# 7. Cross-user delete -> must be 403/404
r = client.delete(f"/conversations/{chat_b}", headers=ha)
print("A deleting B's chat:", r.status_code)
assert r.status_code in (403, 404), "FAIL: A could delete B's chat"
print("PASS: delete ownership enforced")

# 8. Memory isolation
save_memory("User A secret fact about Xanadu", user_a)
mem_a = get_all_memories(user_a)
mem_b = get_all_memories(user_b)
print("A memories:", mem_a)
print("B memories:", mem_b)
assert "User A secret fact about Xanadu" in mem_a, "FAIL: A's memory not saved"
assert "User A secret fact about Xanadu" not in mem_b, "FAIL: B sees A's memory"
ma = client.get("/memories", headers=ha).json()["memories"]
mb = client.get("/memories", headers=hb).json()["memories"]
assert "User A secret fact about Xanadu" in ma, "FAIL: /memories A missing"
assert "User A secret fact about Xanadu" not in mb, "FAIL: /memories B sees A's"
print("PASS: memory isolation")

# 9. RAG isolation
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
    f.write("This is a SECRET document belonging to User A about project Xanadu.")
    tmp_path = f.name

with open(tmp_path, "rb") as f:
    up = client.post("/upload-files", headers=ha, files=[("files", ("secret_a.txt", f, "text/plain"))])
print("Upload A result:", up.json())

ctx_a = search_pdf("Xanadu", user_a)
print("A RAG context:", ctx_a)
assert ctx_a and "Xanadu" in ctx_a, "FAIL: A cannot search own doc"

ctx_b = search_pdf("Xanadu", user_b)
print("B RAG context:", ctx_b)
assert ctx_b is None or "Xanadu" not in ctx_b, "FAIL: B sees A's doc"
print("PASS: RAG isolation")

os.unlink(tmp_path)

print("=" * 60)
print("ALL PRIVACY TESTS PASSED")
print("=" * 60)