import os
import shutil

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

# other imports
from database import *
from models import *
from gemini import *
from rag import *


# FIRST create FastAPI app
app = FastAPI()


# THEN add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.34:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def home():
    return {"message": "MyGPT Backend Running 🚀"}

@app.post("/new-chat")
def new_chat():

    chat_id = create_conversation()

    return {
        "chat_id": chat_id,
        "title": "New Chat"
    }


@app.post("/chat")
def chat(data: ChatRequest):

    # Check whether this is the first user message
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM chats
        WHERE chat_id = ? AND role = 'user'
        """,
        (data.chat_id,)
    )

    first_message = cursor.fetchone()[0] == 0

    # Save user message
    cursor.execute(
        """
        INSERT INTO chats(chat_id, role, message)
        VALUES (?, ?, ?)
        """,
        (
            data.chat_id,
            "user",
            data.message
        )
    )

    conn.commit()

    # First question becomes sidebar title
    if first_message:

        title = data.message.strip()

        if len(title) > 40:
            title = title[:40] + "..."

        update_conversation_title(
            data.chat_id,
            title
        )

    # RAG
    context = search_pdf(data.message)

    # Gemini
    answer = ask_gemini(
        data.message,
        context
    )

    # Save AI response
    cursor.execute(
        """
        INSERT INTO chats(chat_id, role, message)
        VALUES (?, ?, ?)
        """,
        (
            data.chat_id,
            "assistant",
            answer
        )
    )

    conn.commit()

    return {
        "response": answer
    }


@app.get("/history/{chat_id}")
def history(chat_id: int):

    messages = get_chat_messages(chat_id)

    return [
        {
            "role": role,
            "content": message
        }
        for role, message in messages
    ]
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):

    # Only allow PDF files
    if not file.filename.lower().endswith(".pdf"):
        return {
            "error": "Only PDF files are allowed"
        }

    os.makedirs("uploads", exist_ok=True)

    file_path = os.path.join("uploads", file.filename)

    # Save PDF inside uploads folder
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Process PDF using RAG
    chunks = process_pdf(file_path)

    return {
        "message": "PDF uploaded and processed successfully",
        "filename": file.filename,
        "chunks": chunks
    }
@app.get("/conversations")
def conversations():

    chats = get_conversations()

    return [
        {
            "chat_id": chat_id,
            "title": title
        }
        for chat_id, title in chats
    ]

@app.post("/upload-files")
async def upload_files(
    files: list[UploadFile] = File(...)
):
    print("\n==============================")
    print("TOTAL FILES RECEIVED:", len(files))
    print(
        "FILES RECEIVED:",
        [file.filename for file in files]
    )
    print("==============================\n")

    os.makedirs("uploads", exist_ok=True)

    results = []

    for index, file in enumerate(files, start=1):

        print(
            f"Processing {index}/{len(files)}:",
            file.filename
        )

        extension = os.path.splitext(
            file.filename
        )[1].lower()

        if extension != ".pdf":
            results.append({
                "filename": file.filename,
                "status": "skipped",
                "message": "Not a PDF"
            })
            continue

        file_path = os.path.join(
            "uploads",
            file.filename
        )

        try:
            # Save PDF
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(
                    file.file,
                    buffer
                )

            print(
                "Saved:",
                file.filename
            )

            # Process PDF
            chunks = process_pdf(file_path)

            print(
                "Successfully processed:",
                file.filename
            )

            results.append({
                "filename": file.filename,
                "status": "success",
                "chunks": chunks
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
            f"{len(successful)} of {len(files)} PDFs processed",
        "total": len(files),
        "successful": len(successful),
        "files": results
    }

@app.post("/analyze-image")
async def analyze_uploaded_image(
    file: UploadFile = File(...),
    question: str = Form(...)
):

    os.makedirs("uploads", exist_ok=True)

    file_path = os.path.join(
        "uploads",
        file.filename
    )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    answer = analyze_image(
        file_path,
        question
    )

    return {
        "response": answer
    }

@app.delete("/conversations/{chat_id}")
def delete_chat(chat_id: int):

    delete_conversation(chat_id)

    return {
        "message": "Conversation deleted successfully"
    }