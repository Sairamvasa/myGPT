import os
import secrets
import logging

from dotenv import load_dotenv
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security
from database import get_conversation_owner

load_dotenv()
logger = logging.getLogger("MyGPT.Auth")

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
    token_length = len(token)

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            logger.warning(
                "AUTH_FAILURE reason=missing_user_id token_present=%s token_length=%s",
                bool(token),
                token_length,
            )
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

        try:
            return int(user_id)
        except (TypeError, ValueError):
            logger.warning(
                "AUTH_FAILURE reason=invalid_user_id_claim token_present=%s token_length=%s",
                bool(token),
                token_length,
            )
            raise HTTPException(status_code=401, detail="Invalid token")

    except HTTPException:
        raise
    except JWTError as exc:
        logger.warning(
            "AUTH_FAILURE reason=%s token_present=%s token_length=%s",
            type(exc).__name__,
            bool(token),
            token_length,
        )
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
