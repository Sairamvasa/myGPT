import os
import logging
import tempfile
import sqlite3
import bcrypt
import re
import hashlib
import uuid
from decimal import Decimal, InvalidOperation
from contextlib import asynccontextmanager
from PIL import Image

from pydantic import BaseModel, Field

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from jose import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load configuration before importing modules that read environment variables.
load_dotenv()

from vision import analyze_image
from gemini import generate_image
from database import *
from models import *
from agents.agent import Agent
from auth import get_current_user, verify_chat_ownership, JWT_SECRET_KEY, JWT_ALGORITHM
from llm import (
    ask_llm,
    ask_llm_routed,
    stream_llm,
    stream_llm_routed,
    LLMError,
    OLLAMA_MODEL,
    get_num_predict,
    get_routed_provider_metadata,
)
from perf_telemetry import create_context
from agents.rag_verifier import is_answer_safe_for_context
from file_utils import (
    MAX_TOTAL_UPLOAD_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_FILES,
    safe_filename,
    save_upload_file,
)
from rate_limiter import (
    rate_limiter,
    configure_default_limits,
    ip_rate_limit,
    user_rate_limit,
    get_client_ip,
)

logger = logging.getLogger("MyGPT.API")


def _message_diagnostic(message: str) -> str:
    """Return a non-sensitive identifier for lifecycle diagnostics."""
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]


def _log_chat_phase(trace_id: str, phase: str, **fields):
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key not in {"message", "prompt", "token", "authorization", "api_key", "secret"}
    }
    logger.info("CHAT_LIFECYCLE trace_id=%s phase=%s %s", trace_id, phase, safe_fields)


try:
    from voice_agent.routes import router as voice_router
except ImportError as exc:
    voice_router = None
    logger.warning("Voice dependencies are unavailable; voice routes disabled: %s", exc)


def _load_rag_processors():
    try:
        from rag import process_pdf, process_text_file
    except ImportError as exc:
        logger.warning("RAG dependencies are unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Document processing is unavailable. Install backend requirements.",
        ) from exc

    return process_pdf, process_text_file

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

agent = Agent()


_CURRENT_INFO_VALUE_RE = re.compile(
    r"(?P<prefix>\u20b9|rs\.?|inr|\$|usd|eur|gbp|\u20ac|\u00a3)?\s*"
    r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<suffix>%|(?:/|per\s+)?(?:litre|liter|gallon|kg|gram|ounce|oz|barrel|unit|share|coin|btc|eth|bitcoin|rupees?|dollars?|celsius|fahrenheit|degrees?))?",
    re.IGNORECASE,
)


def _normalize_grounding_number(value: str) -> str | None:
    try:
        number = Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return format(number.normalize(), "f")


def _extract_current_info_values(text: str | None) -> set[str]:
    if not text:
        return set()

    values: set[str] = set()
    for match in _CURRENT_INFO_VALUE_RE.finditer(text):
        if not (match.group("prefix") or match.group("suffix")):
            continue
        normalized = _normalize_grounding_number(match.group("number"))
        if normalized is not None:
            values.add(normalized)
    return values


def _fallback_current_info_answer(tool_results: str | None) -> str:
    if not tool_results or "returned no results" in tool_results.lower():
        return "I couldn't verify the current information."

    value_lines = [
        line.strip().strip("*")
        for line in tool_results.splitlines()
        if any(
            match.group("prefix") or match.group("suffix")
            for match in _CURRENT_INFO_VALUE_RE.finditer(line)
        )
    ]
    source_match = re.search(r"Source:\s*(\S+)", tool_results)
    source = source_match.group(1) if source_match else None

    if value_lines:
        answer = f"Based on the retrieved search result: {value_lines[0]}"
        if source:
            answer += f" [Source: {source}]"
        return answer

    return "I couldn't verify the current information."


def _enforce_current_info_grounding(answer: str, tool_results: str | None) -> str:
    if (
        not tool_results
        or "could not be verified" in tool_results.lower()
        or "no results" in tool_results.lower()
    ):
        return "I couldn't verify the current information from a live search."

    stripped_answer = answer.strip()
    if not stripped_answer or stripped_answer.endswith((":", "-", "—", "...")):
        return _fallback_current_info_answer(tool_results)

    answer_values = _extract_current_info_values(answer)
    source_values = _extract_current_info_values(tool_results)
    if not answer_values:
        if not source_values:
            return answer
        # A current-info answer without a verifiable value must not make an
        # unsupported freshness claim.
        freshness_claim = re.search(
            r"\b(?:today|current|latest|now|live|as of)\b",
            answer,
            re.IGNORECASE,
        )
        return (
            "I couldn't verify the current information from the retrieved "
            "search results."
            if freshness_claim
            else answer
        )

    if answer_values.issubset(source_values):
        # Do not accept a date/source claim that is absent from retrieval.
        claimed_dates = set(
            re.findall(
                r"\b(?:January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                answer,
                re.IGNORECASE,
            )
        )
        if claimed_dates and not claimed_dates.issubset(
            set(re.findall(
                r"\b(?:January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                tool_results,
                re.IGNORECASE,
            ))
        ):
            return "I couldn't verify the date associated with the current information."
        return answer

    return _fallback_current_info_answer(tool_results)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting MyGPT API")
    configure_default_limits()
    logger.info("Rate limits configured")
    
    # Verify critical dependencies
    try:
        from llm import _check_config
        _check_config()
        logger.info("Ollama configuration verified")
    except Exception as e:
        logger.warning("Ollama configuration check failed: %s", e)
    
    yield
    
    # Shutdown
    logger.info("Shutting down MyGPT API")


# FIRST create FastAPI app
app = FastAPI(lifespan=lifespan)


def log_security_event(event_type: str, details: dict):
    """Log security-relevant events with structured data."""
    safe_details = {k: v for k, v in details.items() 
                    if k not in ("password", "password_hash", "token", "secret", "key", "api_key")}
    logger.warning("SECURITY_EVENT: type=%s details=%s", event_type, safe_details)


def log_request(request: Request, response_status: int, latency_ms: float):
    """Log request with structured data (no sensitive content)."""
    user_id = getattr(request.state, "user_id", None)
    rate_limit_info = getattr(request.state, "rate_limit_info", None)
    
    logger.info(
        "REQUEST: method=%s path=%s status=%d latency_ms=%.2f user_id=%s rate_limit=%s client_ip=%s",
        request.method,
        request.url.path,
        response_status,
        latency_ms,
        user_id,
        rate_limit_info.get("limit_name") if rate_limit_info else None,
        get_client_ip(request),
    )


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware to log all requests and responses."""
    import time
    start_time = time.monotonic()
    request.state.trace_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    
    try:
        response = await call_next(request)
        latency_ms = (time.monotonic() - start_time) * 1000
        log_request(request, response.status_code, latency_ms)
        return response
    except Exception as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        log_request(request, 500, latency_ms)
        logger.exception("UNHANDLED_ERROR: method=%s path=%s error=%s", 
                        request.method, request.url.path, type(e).__name__)
        raise


DEFAULT_CORS_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://192.168.1.34:3000",
    "https://my-gpt-hazel-six.vercel.app",
    "https://my-pam24ufo6-sairamvasas-projects.vercel.app",
}
CORS_ORIGINS = {
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).split(",")
    if origin.strip()
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def home():
    return {"message": "MyGPT Backend Running 🚀"}


@app.get("/health")
def health():
    """Liveness probe - returns 200 if process is alive."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe - checks critical dependencies."""
    import sqlite3
    from llm import _check_config
    
    # Check database
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        db_ok = False
    
    # Check Ollama config (doesn't require connection)
    try:
        _check_config()
        ollama_ok = True
    except Exception as e:
        logger.error("Ollama config check failed: %s", e)
        ollama_ok = False
    
    if db_ok and ollama_ok:
        return {"status": "ready", "database": "ok", "ollama": "ok"}
    else:
        # Return 503 if not ready
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "ok" if db_ok else "failed",
                "ollama": "ok" if ollama_ok else "failed",
            },
        )
    

# Rate limit dependencies
register_rate_limit = Depends(ip_rate_limit("register"))
login_rate_limit = Depends(ip_rate_limit("login"))
chat_rate_limit = Depends(user_rate_limit("chat"))
stream_rate_limit = Depends(user_rate_limit("stream"))
vision_rate_limit = Depends(user_rate_limit("vision"))
generate_image_rate_limit = Depends(user_rate_limit("generate_image"))
upload_rate_limit = Depends(user_rate_limit("upload"))
upload_files_rate_limit = Depends(user_rate_limit("upload_files"))


@app.post("/register")
def register(data: RegisterRequest, _rl: None = register_rate_limit):
    name = data.name.strip()
    email = data.email.strip().lower()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty.")

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            raise HTTPException(status_code=409, detail="Email already registered.")

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
                name,
                email,
                password_hash
            )
        )

        user_id = cursor.lastrowid

        conn.commit()

        # Generate access token (same as login)
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
            "message": "User registered successfully",
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user_id,
            "name": name,
            "email": email
        }
    except HTTPException:
        raise
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered.")
    except Exception:
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail="Registration failed.")
    finally:
        conn.close()


@app.post("/login")
def login(data: LoginRequest, _rl: None = login_rate_limit):
    email = data.email.strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, email, password_hash FROM users WHERE email = ?",
            (email,),
        )
        user = cursor.fetchone()

        if not user or not bcrypt.checkpw(
            data.password.encode("utf-8"),
            user[3].encode("utf-8"),
        ):
            logger.warning("AUTH_FAILURE reason=invalid_login email_present=%s", bool(email))
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        user_id, name, stored_email, _password_hash = user
        token_data = {
            "user_id": int(user_id),
            "email": stored_email,
            "exp": datetime.utcnow() + timedelta(days=7),
        }
        access_token = jwt.encode(
            token_data,
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

        logger.info(
            "AUTH_SUCCESS user_id_present=%s token_present=%s token_length=%s",
            user_id is not None,
            bool(access_token),
            len(access_token),
        )
        return {
            "success": True,
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": int(user_id),
            "name": name,
            "email": stored_email,
        }
    finally:
        conn.close()


@app.post("/new-chat")
def new_chat(user_id: int = Depends(get_current_user)):

    chat_id = create_conversation(user_id, "New Chat")
    logger.info(
        "CHAT_LIFECYCLE phase=chat_created user_id_present=%s chat_id_present=%s",
        user_id is not None,
        chat_id is not None,
    )

    return {
        "chat_id": chat_id,
        "title": "New Chat",
        "user_id": user_id
    }
    
@app.post("/chat")
def chat(request: Request, data: ChatRequest, user_id: int = Depends(get_current_user), _rl: None = chat_rate_limit):

    verify_chat_ownership(data.chat_id, user_id)
    trace_id = getattr(request.state, "trace_id", None)
    provider_name, provider_model = get_routed_provider_metadata()
    _log_chat_phase(
        trace_id,
        "request_validated",
        user_id_present=user_id is not None,
        chat_id_present=data.chat_id is not None,
        message_length=len(data.message),
        message_hash=_message_diagnostic(data.message),
        provider=provider_name,
        model=provider_model,
    )

    save_message(data.chat_id, "user", data.message)
    _log_chat_phase(trace_id, "user_persisted_before_agent", user_message_persisted=True)

    perf = create_context("chat", OLLAMA_MODEL)
    perf.rag_used = False

    result = agent.run(
        data.message,
        data.chat_id,
        user_id
    )
    _log_chat_phase(
        trace_id,
        "agent_complete",
        action=result.get("action"),
        history_count=len(result.get("history") or []),
        memory_count=len(result.get("memories") or []),
        rag_result_count=1 if result.get("context") else 0,
        contextual_mode=bool(result.get("context")),
        prompt_has_current_message=data.message in result.get("prompt", ""),
        prompt_has_history=bool(result.get("history")),
        provider=provider_name,
        model=provider_model,
    )
    perf.rag_used = result.get("context") is not None

    # Smart per-request generation limit based on action and message content.
    action = result.get("action", "chat")
    num_predict = get_num_predict(action, data.message)

    if result.get("answer"):
        answer = result["answer"]
    else:
        try:
            answer = ask_llm_routed(result["prompt"], action, perf_context=perf, num_predict=num_predict)
        except LLMError as e:
            perf.add_error(e.kind)
            perf.emit()
            # For current_info failures, return the retrieved search results
            if e.kind == "current_info_failed":
                tool_results = result.get("tool_results")
                if tool_results and "CURRENT INFORMATION SEARCH RESULTS" in tool_results:
                    answer = f"⚠️ {e.user_message}\n\n**Retrieved Search Results:**\n{tool_results}"
                else:
                    answer = f"⚠️ {e.user_message}"
            else:
                raise HTTPException(
                    status_code=e.status_code,
                    detail={
                        "error": True,
                        "code": e.kind,
                        "message": "LLM request failed.",
                        "retry_after_seconds": e.retry_after,
                    },
                )

    if not answer or not answer.strip():
        answer = (
            "⚠️ I couldn't generate an answer for this request. "
            "Please try again."
        )
    perf.output_length = len(answer)
    
    # Verify RAG answers against retrieved context
    if action == "rag" and result.get("context"):
        is_safe = is_answer_safe_for_context(answer, result["context"], data.message)
        if not is_safe:
            # Fallback: provide a safe answer based only on context
            answer = f"Based on the uploaded document, I can see the code defines functions and variables. The exact output would require executing the code. The document shows: {result['context'][:500]}..."

    if action in ("current_info", "web_research"):
        answer = _enforce_current_info_grounding(answer, result.get("tool_results"))
    
    perf.emit()

    save_message(
        data.chat_id,
        "assistant",
        answer
    )
    _log_chat_phase(
        trace_id,
        "assistant_persisted",
        assistant_message_persisted=True,
        response_status=200,
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
    user_id: int = Depends(get_current_user),
    _rl: None = upload_rate_limit,
):
    filename = safe_filename(file.filename)

    # Only allow PDF files
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    process_pdf, _ = _load_rag_processors()

    # Per-user upload directory
    user_dir = os.path.join("uploads", str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, filename)

# Save PDF inside user's upload folder
    save_upload_file(file, file_path, base_dir=user_dir)

    # Process PDF using RAG (scoped to this user)
    chunks = process_pdf(file_path, user_id, source_filename=filename)

    return {
        "message": "PDF uploaded and processed successfully",
        "filename": filename,
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
    user_id: int = Depends(get_current_user),
    _rl: None = upload_files_rate_limit,
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"You can upload at most {MAX_UPLOAD_FILES} files at a time.",
        )

    process_pdf, process_text_file = _load_rag_processors()

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
    total_bytes = 0

    for index, file in enumerate(files, start=1):

        logger.info("Processing upload %s/%s: %s", index, len(files), file.filename)

        try:
            # Guard: filename must be present
            if not file.filename:
                results.append({
                    "filename": "unknown",
                    "status": "error",
                    "message": "File has no filename"
                })
                continue

            filename = safe_filename(file.filename)
            extension = os.path.splitext(filename)[1].lower()

            if extension != ".pdf" and extension not in TEXT_EXTENSIONS:
                results.append({
                    "filename": filename,
                    "status": "skipped",
"message": f"Unsupported file type: {extension}"
                })
                continue

            file_path = os.path.join(
                user_dir,
                filename
            )

            remaining_bytes = MAX_TOTAL_UPLOAD_BYTES - total_bytes
            if remaining_bytes <= 0:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"The combined upload exceeds the "
                        f"{MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                    ),
                )

            total_bytes += save_upload_file(
                file,
                file_path,
                max_bytes=min(MAX_UPLOAD_BYTES, remaining_bytes),
                base_dir=user_dir,
            )

            if extension == ".pdf":
                # Process using RAG PDF pipeline
                chunks = process_pdf(file_path, user_id, source_filename=filename)
                logger.info("Successfully processed PDF: %s", filename)
                results.append({
                    "filename": filename,
                    "status": "success",
                    "type": "pdf",
                    "chunks": chunks
                })

            elif extension in TEXT_EXTENSIONS:
                # Process as plain text / code file
                chunks = process_text_file(file_path, user_id, source_filename=filename)
                logger.info("Successfully processed text/code file: %s", filename)
                results.append({
                    "filename": filename,
                    "status": "success",
                    "type": "text",
                    "chunks": chunks
                })

        except HTTPException:
            raise
        except Exception:
            logger.exception("Error processing upload %s", file.filename)

            results.append({
                "filename": safe_filename(file.filename, "unknown"),
                "status": "error",
                "message": "Unable to process this file."
            })


    successful = [
        result
        for result in results
        if result["status"] == "success"
    ]

    logger.info("Successfully processed %s of %s uploads", len(successful), len(files))

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
def vision(
    file: UploadFile = File(...),
    prompt: str = Form("Describe this image."),
    user_id: int = Depends(get_current_user),
    _rl: None = vision_rate_limit,
):
    filename = safe_filename(file.filename, "image")
    extension = os.path.splitext(filename)[1].lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG, and WEBP images are allowed.",
        )

    user_dir = os.path.join("uploads", str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    fd, file_path = tempfile.mkstemp(
        suffix=extension,
        prefix="vision_",
        dir=user_dir,
    )
    os.close(fd)

    try:
        save_upload_file(file, file_path, base_dir=user_dir)

        # Validate image content before processing
        try:
            with Image.open(file_path) as img:
                img.verify()
                if img.width > 8192 or img.height > 8192:
                    raise HTTPException(
                        status_code=400,
                        detail="Image dimensions too large.",
                    )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid or corrupt image file.",
            )

        answer = analyze_image(file_path, prompt)
        return {"answer": answer}
    except LLMError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": True,
                "code": e.kind,
                "message": "Image analysis failed.",
                "retry_after_seconds": e.retry_after,
            },
        )
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass


@app.post("/generate-image")
def generate_image(
    prompt: str = Form(...),
    aspect_ratio: str = Form("1:1"),
    user_id: int = Depends(get_current_user),
    _rl: None = generate_image_rate_limit,
):
    """
    Generate an image using Gemini's image generation model.
    
    Args:
        prompt: Text description of the image to generate
        aspect_ratio: Aspect ratio for the generated image (1:1, 16:9, 9:16, 4:3, 3:4)
    
    Returns:
        base64 encoded image data
    """
    try:
        from gemini import generate_image
        image_b64 = generate_image(prompt, aspect_ratio)
        return {
            "image": image_b64,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio
        }
    except Exception as e:
        logger.exception("Image generation failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error": True,
                "code": "image_generation_failed",
                "message": f"Image generation failed: {str(e)}",
            },
        )

@app.post("/stream")
def stream(request: Request, data: ChatRequest, user_id: int = Depends(get_current_user), _rl: None = stream_rate_limit):

    verify_chat_ownership(data.chat_id, user_id)
    trace_id = getattr(request.state, "trace_id", None)
    provider_name, provider_model = get_routed_provider_metadata()
    _log_chat_phase(
        trace_id,
        "stream_start",
        action="pending",
        provider=provider_name,
        model=provider_model,
    )
    _log_chat_phase(
        trace_id,
        "request_validated",
        user_id_present=user_id is not None,
        chat_id_present=data.chat_id is not None,
        message_length=len(data.message),
        message_hash=_message_diagnostic(data.message),
        provider=provider_name,
        model=provider_model,
    )
    save_message(data.chat_id, "user", data.message)
    _log_chat_phase(trace_id, "user_persisted_before_agent", user_message_persisted=True)

    perf = create_context("stream", OLLAMA_MODEL)

    result = agent.run(
        data.message,
        data.chat_id,
        user_id
    )
    _log_chat_phase(
        trace_id,
        "agent_complete",
        action=result.get("action"),
        history_count=len(result.get("history") or []),
        memory_count=len(result.get("memories") or []),
        rag_result_count=1 if result.get("context") else 0,
        contextual_mode=bool(result.get("context")),
        prompt_has_current_message=data.message in result.get("prompt", ""),
        prompt_has_history=bool(result.get("history")),
        provider=provider_name,
        model=provider_model,
    )
    perf.rag_used = result.get("context") is not None

    # If agent returned a direct answer
    if result.get("answer"):

        # Save immediately for direct responses
        save_message(data.chat_id, "assistant", result["answer"])
        perf.emit()

        # Auto-title conversation on first user message
        if is_first_message(data.chat_id):
            short_title = data.message[:60].strip()
            update_conversation_title(data.chat_id, short_title)

        def direct_response():
            yield result["answer"]

        return StreamingResponse(
            direct_response(),
            media_type="text/plain"
        )

    # Final prompt created by Agent
    prompt = result["prompt"]

    # Smart per-request generation limit based on action and message content.
    action = result.get("action", "chat")
    num_predict = get_num_predict(action, data.message)

    # Auto-title conversation on first user message (before streaming starts)
    first = is_first_message(data.chat_id)

    async def generate():

        full_answer = ""
        chunk_count = 0
        had_error = False
        client_disconnected = False
        fallback_answer = "I couldn't generate an answer for this request. Please try again."
        buffer_for_grounding = action in ("current_info", "web_research")

        try:
            for chunk in stream_llm_routed(prompt, action, perf_context=perf, num_predict=num_predict):
                if await request.is_disconnected():
                    client_disconnected = True
                    break
                if not chunk:
                    continue
                chunk_count += 1
                full_answer += chunk
                if chunk_count == 1:
                    _log_chat_phase(
                        trace_id,
                        "first_backend_chunk",
                        action=action,
                        provider=provider_name,
                        model=provider_model,
                        chunk_length=len(chunk),
                    )
                if not buffer_for_grounding:
                    yield chunk
        except LLMError as e:
            had_error = True
            perf.add_error(e.kind)
            perf.emit()
            # For current_info failures, show the retrieved search results to the user
            if e.kind == "current_info_failed":
                tool_results = result.get("tool_results")
                if buffer_for_grounding and full_answer:
                    yield full_answer
                if tool_results and "CURRENT INFORMATION SEARCH RESULTS" in tool_results:
                    # Extract and present the search results
                    error_text = (
                        f"\n\n---\n\n⚠️ {e.user_message}\n\n"
                        f"**Retrieved Search Results:**\n{tool_results}"
                    )
                else:
                    error_text = f"\n\n---\n\n⚠️ {e.user_message}"
                yield error_text
                full_answer += error_text
                fallback_answer = ""
            else:
                fallback_answer = "\n\n---\n\n⚠️ LLM request failed."
                if buffer_for_grounding and full_answer:
                    yield full_answer
                yield fallback_answer
                full_answer += fallback_answer
        except Exception as e:
            had_error = True
            perf.add_error("unknown_error")
            perf.emit()
            fallback_answer = (
                "\n\n---\n\n⚠️ The AI service is temporarily "
                "unavailable. Please try again."
            )
            if buffer_for_grounding and full_answer:
                yield full_answer
            yield fallback_answer
            full_answer += fallback_answer
        finally:
            if buffer_for_grounding and not had_error and full_answer and not client_disconnected:
                full_answer = _enforce_current_info_grounding(
                    full_answer,
                    result.get("tool_results"),
                )
                yield full_answer

            if not full_answer.strip() and not client_disconnected:
                full_answer = fallback_answer.strip()
                yield full_answer

            perf.emit()
            # The user turn was persisted before agent execution. Only persist
            # the assistant reply when we actually produced one
            # and it wasn't an intentional client cancellation.
            if full_answer.strip() and not client_disconnected:
                perf.output_length = len(full_answer)
                _log_chat_phase(
                    trace_id,
                    "stream_finished",
                    action=action,
                    provider=provider_name,
                    model=provider_model,
                    chunk_count=chunk_count,
                    answer_length=len(full_answer),
                )
                save_message(
                    data.chat_id,
                    "assistant",
                    full_answer
                )
                _log_chat_phase(
                    trace_id,
                    "assistant_persisted",
                    assistant_message_persisted=True,
                    response_status=200,
                )

        # Update conversation title after the first exchange
        if first and data.message:
            short_title = data.message[:60].strip()
            update_conversation_title(data.chat_id, short_title)

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
def login(data: LoginRequest, _rl: None = login_rate_limit):

    email = data.email.strip().lower()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?",
        (email,)
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

if voice_router is not None:
    app.include_router(voice_router)
