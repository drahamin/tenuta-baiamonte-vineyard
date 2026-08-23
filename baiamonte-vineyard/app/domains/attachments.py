"""Shared, recoverable filesystem storage for uploaded domain attachments."""

from __future__ import annotations

import hashlib
import os
import re
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
    """Persist one sanitized attachment and return its durable metadata."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or fallback_name).name)[:180]
    safe_name = safe_name or fallback_name
    ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    stored_path = ATTACHMENT_ROOT / f"{attachment_id}-{safe_name}"
    stored_path.write_bytes(data)
    return StoredAttachment(path=stored_path, filename=safe_name, sha256=hashlib.sha256(data).hexdigest())
