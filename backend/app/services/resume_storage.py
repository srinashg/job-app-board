"""Filesystem storage for uploaded resume files.

Files live outside the database so a deletion request can be honoured by
removing the bytes, not just clearing a column.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from app.core.config import settings

EXTENSION_BY_CONTENT_TYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


def storage_root() -> Path:
    root = Path(settings.resume_storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _user_dir(user_id: uuid.UUID) -> Path:
    directory = storage_root() / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(user_id: uuid.UUID, resume_id: uuid.UUID, data: bytes, content_type: str) -> str:
    """Write the file and return its path relative to the storage root."""
    extension = EXTENSION_BY_CONTENT_TYPE.get(content_type, "")
    path = _user_dir(user_id) / f"{resume_id}{extension}"
    path.write_bytes(data)
    os.chmod(path, 0o600)
    return str(path.relative_to(storage_root()))


def read(relative_path: str | None) -> bytes | None:
    if not relative_path:
        return None
    path = _resolve(relative_path)
    if path is None or not path.is_file():
        return None
    return path.read_bytes()


def delete(relative_path: str | None) -> bool:
    """Remove a stored file. Returns whether anything was deleted."""
    if not relative_path:
        return False
    path = _resolve(relative_path)
    if path is None or not path.is_file():
        return False
    path.unlink()
    return True


def delete_all_for_user(user_id: uuid.UUID) -> int:
    directory = storage_root() / str(user_id)
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.iterdir():
        if path.is_file():
            path.unlink()
            removed += 1
    directory.rmdir()
    return removed


def _resolve(relative_path: str) -> Path | None:
    """Resolve a stored path, refusing anything that escapes the storage root."""
    root = storage_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
