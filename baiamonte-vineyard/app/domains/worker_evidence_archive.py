"""Encrypted, deduplicated camera evidence for administrator review only.

The archive preserves a camera frame as evidence but deliberately performs no
face recognition, biometric templating, plate OCR, or employment decision.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from PIL import Image

from ..db import fetch_one, transaction
from ..service import estate_id


ARCHIVE_ROOT = Path(os.environ.get("WORKER_EVIDENCE_ROOT", "/data/worker-camera-evidence"))
KEY_PATH = Path(os.environ.get("WORKER_EVIDENCE_KEY_PATH", "/data/worker-camera-evidence.key"))
MAX_FRAME_BYTES = 15 * 1024 * 1024
DEFAULT_RETENTION_DAYS = 90
REVIEWED_RETENTION_DAYS = 180


def _encryption_key() -> bytes:
    """Load or create the persistent add-on-local AES-256 key with owner-only permissions."""
    try:
        key = KEY_PATH.read_bytes()
        if len(key) == 32:
            return key
    except OSError:
        pass
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    temporary = KEY_PATH.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(key)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(KEY_PATH)
    KEY_PATH.chmod(0o600)
    return key


def _dimensions(content: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(BytesIO(content)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def archive_camera_frame(
    content: bytes,
    *,
    content_type: str,
    camera_entity_id: str,
    observation_zone: str,
    captured_at: datetime | None,
    source_kind: str,
) -> str | None:
    """Encrypt one original frame and return its content hash; identical frames share one file."""
    if not content or len(content) > MAX_FRAME_BYTES or not str(content_type).casefold().startswith("image/"):
        return None
    digest = hashlib.sha256(content).hexdigest()
    captured = captured_at or datetime.now(timezone.utc).replace(tzinfo=None)
    if captured.tzinfo:
        captured = captured.astimezone(timezone.utc).replace(tzinfo=None)
    relative = Path(digest[:2]) / f"{digest}.aes"
    destination = ARCHIVE_ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    encrypted_bytes = destination.stat().st_size if destination.exists() else 0
    if not destination.exists():
        nonce = os.urandom(12)
        encrypted = nonce + AESGCM(_encryption_key()).encrypt(nonce, content, digest.encode("ascii"))
        temporary = destination.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
        destination.chmod(0o600)
        encrypted_bytes = len(encrypted)
    width, height = _dimensions(content)
    retention = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=DEFAULT_RETENTION_DAYS)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO worker_camera_evidence "
            "(id,estate_id,camera_entity_id,observation_zone,captured_at,source_kind,content_type,original_bytes,"
            "encrypted_bytes,width_px,height_px,storage_path,retention_until) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE retention_until=GREATEST(retention_until,VALUES(retention_until)),"
            "camera_entity_id=VALUES(camera_entity_id),observation_zone=VALUES(observation_zone)",
            (digest, estate_id(), camera_entity_id[:255], observation_zone[:80], captured, source_kind[:80],
             content_type[:80], len(content), encrypted_bytes, width, height, str(relative), retention),
        )
    return digest


def evidence_metadata(evidence_id: str) -> dict[str, Any] | None:
    if len(evidence_id) != 64 or any(character not in "0123456789abcdef" for character in evidence_id):
        return None
    return fetch_one(
        "SELECT id,camera_entity_id,observation_zone,captured_at,source_kind,content_type,original_bytes,"
        "width_px,height_px,retention_until,legal_hold,review_status FROM worker_camera_evidence "
        "WHERE estate_id=%s AND id=%s",
        (estate_id(), evidence_id),
    )


def read_camera_evidence(evidence_id: str) -> tuple[dict[str, Any], bytes] | None:
    row = fetch_one(
        "SELECT * FROM worker_camera_evidence WHERE estate_id=%s AND id=%s",
        (estate_id(), evidence_id),
    )
    if not row:
        return None
    path = ARCHIVE_ROOT / str(row.get("storage_path") or "")
    try:
        encrypted = path.read_bytes()
        content = AESGCM(_encryption_key()).decrypt(encrypted[:12], encrypted[12:], evidence_id.encode("ascii"))
    except (OSError, ValueError, InvalidTag):
        return None
    if hashlib.sha256(content).hexdigest() != evidence_id:
        return None
    return row, content


def extend_evidence_review(evidence_id: str, status: str) -> None:
    retention = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=REVIEWED_RETENTION_DAYS)
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE worker_camera_evidence SET review_status=%s,retention_until=GREATEST(retention_until,%s) "
            "WHERE estate_id=%s AND id=%s",
            (status, retention, estate_id(), evidence_id),
        )


def purge_expired_evidence(limit: int = 50) -> int:
    """Remove a bounded batch so cleanup never creates a large I/O spike."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    # Lock and delete metadata first; an orphaned encrypted file is safer than a
    # metadata row pointing to a missing file and can be reclaimed later.
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT id,storage_path FROM worker_camera_evidence WHERE estate_id=%s AND legal_hold=0 "
            "AND retention_until<%s ORDER BY retention_until LIMIT %s FOR UPDATE",
            (estate_id(), now, max(1, min(limit, 200))),
        )
        rows = list(cursor.fetchall())
        if rows:
            placeholders = ",".join(["%s"] * len(rows))
            cursor.execute(
                f"DELETE FROM worker_camera_evidence WHERE estate_id=%s AND id IN ({placeholders})",
                (estate_id(), *(row["id"] for row in rows)),
            )
    for row in rows:
        try:
            (ARCHIVE_ROOT / str(row.get("storage_path") or "")).unlink(missing_ok=True)
        except OSError:
            pass
    return len(rows)
