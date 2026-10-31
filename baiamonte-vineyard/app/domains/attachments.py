"""Shared, recoverable filesystem storage for uploaded domain attachments."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path


ATTACHMENT_ROOT = Path(os.getenv("ATTACHMENT_ROOT", "/data/baiamonte-attachments"))
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class StoredAttachment:
    path: Path
    filename: str
    sha256: str

    def discard(self) -> None:
        """Remove a file whose database transaction did not complete."""
        self.path.unlink(missing_ok=True)


def store_attachment(data: bytes, attachment_id: str, filename: str, fallback_name: str) -> StoredAttachment:
    """Atomically publish one crash-durable attachment and return its metadata."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or fallback_name).name)[:180]
    safe_name = safe_name or fallback_name
    ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    stored_path = ATTACHMENT_ROOT / f"{attachment_id}-{safe_name}"
    temporary = ATTACHMENT_ROOT / f".{attachment_id}-{secrets.token_hex(8)}.tmp"
    published = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            view = memoryview(data)
            while view:
                written = handle.write(view)
                if written is None or written < 1:
                    raise OSError("attachment write did not progress")
                view = view[written:]
            handle.flush()
            os.fsync(handle.fileno())
        if stored_path.exists():
            raise FileExistsError("attachment path already exists")
        os.replace(temporary, stored_path)
        published = True
        directory = os.open(ATTACHMENT_ROOT, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        if published:
            stored_path.unlink(missing_ok=True)
        raise
    return StoredAttachment(path=stored_path, filename=safe_name, sha256=hashlib.sha256(data).hexdigest())
