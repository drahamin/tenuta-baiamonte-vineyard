"""Administrator-only Facebook and Instagram routes."""

from __future__ import annotations

from pathlib import Path
import re
import tempfile
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from ..access import authorize_admin
from ..service import json_ready
from ..social import import_relationship_export_file, publish_facebook, publish_instagram, publish_social_photo, social_dashboard


router = APIRouter(prefix="/api/v1/social", tags=["social"])
MAX_RELATIONSHIP_EXPORT_BYTES = 512 * 1024 * 1024
MAX_RELATIONSHIP_CHUNK_BYTES = 768 * 1024
RELATIONSHIP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "baiamonte-social-imports"


def _relationship_upload_path(upload_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9-]{16,80}", upload_id or ""):
        raise HTTPException(422, "Invalid upload identifier; start the import again")
    return RELATIONSHIP_UPLOAD_DIR / f"{upload_id}.part"


def _remove_stale_relationship_uploads() -> None:
    RELATIONSHIP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 24 * 60 * 60
    for candidate in RELATIONSHIP_UPLOAD_DIR.glob("*.part"):
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


@router.get("", dependencies=[Depends(authorize_admin)])
def social_center(refresh: bool = Query(False)) -> dict[str, Any]:
    return social_dashboard(refresh=refresh)


@router.post("/facebook", dependencies=[Depends(authorize_admin)])
def social_publish_facebook(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_facebook(str(payload.get("message") or ""), str(payload.get("link") or "") or None, str(payload.get("image_url") or "") or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Facebook publish failed: " + str(error)[:300]) from error


@router.post("/instagram", dependencies=[Depends(authorize_admin)])
def social_publish_instagram(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_instagram(str(payload.get("image_url") or ""), str(payload.get("caption") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Instagram publish failed: " + str(error)[:300]) from error


@router.post("/photo", dependencies=[Depends(authorize_admin)])
async def social_publish_photo(channel: str = Form(...), caption: str = Form(...), link: str = Form(""), file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Choose a photo smaller than 12 MB")
    try:
        return publish_social_photo(channel, data, file.filename or "social-photo.jpg", file.content_type or "application/octet-stream", caption, link or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Social photo publish failed: " + str(error)[:300]) from error


@router.post("/audience-import", dependencies=[Depends(authorize_admin)])
async def social_audience_import(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    temporary_path: Path | None = None
    try:
        total = 0
        with tempfile.NamedTemporaryFile(prefix="meta-relationships-", suffix=Path(file.filename or "export.zip").suffix, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_RELATIONSHIP_EXPORT_BYTES:
                    raise HTTPException(413, "Choose a Meta export smaller than 512 MB")
                temporary.write(chunk)
        username = (request.headers.get("X-Remote-User-Name") or "administrator").strip()
        return json_ready(import_relationship_export_file(temporary_path, file.filename or "instagram-export.zip", username))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(500, "Instagram relationship import failed: " + str(error)[:300]) from error
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


@router.post("/audience-import-chunk", dependencies=[Depends(authorize_admin)])
async def social_audience_import_chunk(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    offset: int = Form(...),
    total_size: int = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Receive a large Meta archive below Home Assistant ingress's per-request limit."""
    if total_size < 1 or total_size > MAX_RELATIONSHIP_EXPORT_BYTES:
        raise HTTPException(413, "Choose a Meta export smaller than 512 MB")
    if total_chunks < 1 or total_chunks > 2048 or chunk_index < 0 or chunk_index >= total_chunks or offset < 0:
        raise HTTPException(422, "Invalid upload sequence; start the import again")
    data = await file.read(MAX_RELATIONSHIP_CHUNK_BYTES + 1)
    if not data or len(data) > MAX_RELATIONSHIP_CHUNK_BYTES:
        raise HTTPException(413, "An import piece was too large; start the import again")
    _remove_stale_relationship_uploads()
    temporary_path = _relationship_upload_path(upload_id)
    if chunk_index == 0:
        temporary_path.unlink(missing_ok=True)
    current_size = temporary_path.stat().st_size if temporary_path.exists() else 0
    if current_size != offset or current_size + len(data) > total_size:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(409, "The import was interrupted; please select the export and try again")
    with temporary_path.open("ab") as destination:
        destination.write(data)
    received = current_size + len(data)
    if chunk_index < total_chunks - 1:
        return {"complete": False, "received": received, "total": total_size}
    if received != total_size:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(409, "The import was incomplete; please select the export and try again")
    try:
        username = (request.headers.get("X-Remote-User-Name") or "administrator").strip()
        result = json_ready(import_relationship_export_file(temporary_path, Path(filename).name, username))
        result["complete"] = True
        return result
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(500, "Instagram relationship import failed: " + str(error)[:300]) from error
    finally:
        temporary_path.unlink(missing_ok=True)
