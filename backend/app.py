import email
import os
import shutil
import bcrypt

from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jose import jwt, JWTError
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security

from vision import analyze_image
from database import *
from models import *
from gemini import *
from rag import *
from agents.agent import Agent

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mygpt-super-secure-jwt-secret-key-2026")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        return user_id

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

def verify_chat_ownership(chat_id, user_id):
    """Ensure the conversation belongs to the authenticated user."""
    owner = get_conversation_owner(chat_id)

    if owner is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    if owner != user_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this conversation"
        )

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

agent = Agent()


# FIRST create FastAPI app
app = FastAPI()


# THEN add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.34:3000",
        "https://my-gpt-hazel-six.vercel.app",
        "https://my-pam24ufo6-sairamvasas-projects.vercel.app",
    ],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def home():
    return {"message": "MyGPT Backend Running 🚀"}


@app.post("/register")
def register(data: RegisterRequest):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (data.email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return {
                "success": False,
                "message": "Email already registered"
            }

        # Hash password
        password_hash = bcrypt.hashpw(
            data.password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        # Save user
        cursor.execute(
            """
            INSERT INTO users(name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (
                data.name,
                data.email,
                password_hash
            )
        )

        user_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "User registered successfully",
            "user_id": user_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Registration failed: {str(e)}"
        }



@app.post("/new-chat")
def new_chat(user_id: int = Depends(get_current_user)):

    chat_id = create_conversation(user_id, "New Chat")

    return {
        "chat_id": chat_id,
        "title": "New Chat",
        "user_id": user_id
    }
    
@app.post("/chat")
def chat(data: ChatRequest, user_id: int = Depends(get_current_user)):

    verify_chat_ownership(data.chat_id, user_id)

    result = agent.run(
        data.message,
        data.chat_id,
        user_id
    )

    answer = ask_gemini(
        result["prompt"]
    )

    save_message(
        data.chat_id,
        "user",
        data.message
    )

    save_message(
        data.chat_id,
        "assistant",
        answer
    )

    return {
        "answer": answer
    }
@app.get("/history/{chat_id}")
def history(chat_id: int, user_id: int = Depends(get_current_user)):

    verify_chat_ownership(chat_id, user_id)

    messages = get_chat_messages(chat_id)

    return [
        {
            "role": role,
            "content": message
        }
        for role, message in messages
    ]
@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user)
):

    # Only allow PDF files
    if not file.filename.lower().endswith(".pdf"):
        return {
            "error": "Only PDF files are allowed"
        }

    # Per-user upload directory
    user_dir = os.path.join("uploads", str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, file.filename)

    # Save PDF inside user's upload folder
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process PDF using RAG (scoped to this user)
    chunks = process_pdf(file_path, user_id)

    return {
        "message": "PDF uploaded and processed successfully",
        "filename": file.filename,
        "chunks": chunks
    }
@app.get("/conversations")
def conversations(user_id: int = Depends(get_current_user)):

    chats = get_conversations(user_id)

    return [
        {
            "chat_id": chat_id,
            "title": title
        }
        for chat_id, title in chats
    ]

@app.post("/upload-files")
async def upload_files(
    files: list[UploadFile] = File(...),
    user_id: int = Depends(get_current_user)
):
    print("\n==============================")
    print("TOTAL FILES RECEIVED:", len(files))
    print(
        "FILES RECEIVED:",
        [file.filename for file in files]
    )
    print("==============================\n")

    # Per-user upload directory
    user_dir = os.path.join("uploads", str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    # Supported plain-text / code extensions
    TEXT_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".html", ".htm", ".css", ".scss", ".sass",
        ".json", ".jsonc", ".csv", ".tsv",
        ".md", ".markdown", ".txt", ".text",
        ".xml", ".yaml", ".yml", ".toml", ".ini",
        ".sh", ".bash", ".bat", ".ps1",
        ".c", ".cpp", ".h", ".java", ".go",
        ".rs", ".rb", ".php", ".swift", ".kt",
        ".sql", ".env", ".gitignore", ".dockerfile",
        ".r", ".m", ".scala", ".lua",
    }

    results = []

    for index, file in enumerate(files, start=1):

        print(
            f"Processing {index}/{len(files)}:",
            file.filename
        )

        extension = os.path.splitext(
            file.filename
        )[1].lower()

        file_path = os.path.join(
            user_dir,
            file.filename
        )

        try:
            # Save file to disk
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(
                    file.file,
                    buffer
                )

            print("Saved:", file.filename)

            if extension == ".pdf":
                # Process using RAG PDF pipeline
                chunks = process_pdf(file_path, user_id)
                print("Successfully processed PDF:", file.filename)
                results.append({
                    "filename": file.filename,
                    "status": "success",
                    "type": "pdf",
                    "chunks": chunks
                })

            elif extension in TEXT_EXTENSIONS:
                # Process as plain text / code file
                chunks = process_text_file(file_path, user_id)
                print("Successfully processed text/code file:", file.filename)
                results.append({
                    "filename": file.filename,
                    "status": "success",
                    "type": "text",
                    "chunks": chunks
                })

            else:
                results.append({
                    "filename": file.filename,
                    "status": "skipped",
                    "message": f"Unsupported file type: {extension}"
                })

        except Exception as e:

            print(
                "ERROR processing",
                file.filename,
                ":",
                str(e)
            )

            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e)
            })

    successful = [
        result
        for result in results
        if result["status"] == "success"
    ]

    print(
        "SUCCESSFULLY PROCESSED:",
        len(successful)
    )

    return {
        "message":
            f"{len(successful)} of {len(files)} file(s) processed",
        "total": len(files),
        "successful": len(successful),
        "files": results
    }


@app.delete("/conversations/{chat_id}")
def delete_chat(chat_id: int, user_id: int = Depends(get_current_user)):

    verify_chat_ownership(chat_id, user_id)

    delete_conversation(chat_id)

    return {
        "message": "Conversation deleted successfully"
    }

@app.post("/vision")
def vision(file: UploadFile = File(...), prompt: str = Form("Describe this image.")):

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    answer = analyze_image(file_path, prompt)

    return {
        "answer": answer
    }
    
@app.post("/stream")
def stream(data: ChatRequest, user_id: int = Depends(get_current_user)):

    verify_chat_ownership(data.chat_id, user_id)

    result = agent.run(
        data.message,
        data.chat_id,
        user_id
    )

    # If agent returned a direct answer
    if result.get("answer"):

        def direct_response():
            yield result["answer"]

        return StreamingResponse(
            direct_response(),
            media_type="text/plain"
        )

    # Final prompt created by Agent
    prompt = result["prompt"]

    def generate():

        full_answer = ""

        for chunk in stream_gemini(prompt):

            full_answer += chunk
            yield chunk

        # Save messages after streaming completes
        save_message(
            data.chat_id,
            "user",
            data.message
        )

        save_message(
            data.chat_id,
            "assistant",
            full_answer
        )

    return StreamingResponse(
        generate(),
        media_type="text/plain"
    )
    
@app.get("/memories")
def memories(user_id: int = Depends(get_current_user)):

    from database import get_all_memories

    return {
        "memories": get_all_memories(user_id)
    }


@app.post("/login")
def login(data: LoginRequest):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?",
        (data.email,)
    )

    user = cursor.fetchone()
    conn.close()

    if not user:
        return {
            "success": False,
            "message": "Invalid email or password"
        }

    user_id, name, email, password_hash = user

    password_valid = bcrypt.checkpw(
        data.password.encode("utf-8"),
        password_hash.encode("utf-8")
    )

    if not password_valid:
        return {
            "success": False,
            "message": "Invalid email or password"
        }

    token_data = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }

    access_token = jwt.encode(
        token_data,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id,
        "name": name,
        "email": email
    }


@app.get("/me")
def get_me(user_id: int = Depends(get_current_user)):

    return {
        "success": True,
        "message": "Token is valid",
        "user_id": user_id
    }