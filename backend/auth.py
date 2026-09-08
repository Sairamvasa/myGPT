import os
import secrets

from dotenv import load_dotenv
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security
from database import get_conversation_owner

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()

if not JWT_SECRET_KEY:
    if APP_ENV == "production":
        raise RuntimeError("JWT_SECRET_KEY must be configured in production.")

    # Development remains convenient, but no predictable secret is shipped.
    JWT_SECRET_KEY = secrets.token_urlsafe(32)

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
