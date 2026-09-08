"""Helpers for safely handling user-uploaded files."""

import os
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile


MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


def safe_filename(filename: str | None, default: str = "upload") -> str:
    """Return a filesystem-safe basename while preserving its extension."""
    raw_name = (filename or "").replace("\\", "/")
    name = Path(raw_name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip(" .")

    if not name or name in {".", ".."}:
        name = default

    return name[:160]


def save_upload_file(
    upload: UploadFile,
    destination: str | Path,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> int:
    """Save an upload with a hard size limit and return its byte count."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    try:
        with destination.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break

                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds the {max_bytes // (1024 * 1024)} MB limit.",
                    )

                output.write(chunk)
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return total
