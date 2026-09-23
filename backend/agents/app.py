"""Compatibility entrypoint for older deployment commands.

The application used to have a second, unauthenticated FastAPI app here.
Keep the import path working while ensuring every deployment uses the secured
application from ``backend/app.py``.
"""

from app import app

__all__ = ["app"]
