"""Administrator-only Facebook and Instagram routes."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile

from ..access import authorize_admin
from ..service import json_ready
from ..social import import_relationship_export_file, publish_facebook, publish_instagram, publish_social_photo, social_dashboard, social_media


router = APIRouter(prefix="/api/v1/social", tags=["social"])
MAX_RELATIONSHIP_EXPORT_BYTES = 512 * 1024 * 1024
MAX_RELATIONSHIP_CHUNK_BYTES = 768 * 1024
RELATIONSHIP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "baiamonte-social-imports"


def _relationship_upload_path(upload_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9-]{16,80}", upload_id or ""):
        raise HTTPException(422, "Invalid upload identifier; start the import again")
    return RELATIONSHIP_UPLOAD_DIR / f"{upload_id}.part"


def _relationship_chunk_path(upload_id: str, chunk_index: int) -> Path:
    _relationship_upload_path(upload_id)
    return RELATIONSHIP_UPLOAD_DIR / f"{upload_id}.{chunk_index:04d}.chunk"


def _remove_stale_relationship_uploads() -> None:
    RELATIONSHIP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 24 * 60 * 60
    candidates = [
        *RELATIONSHIP_UPLOAD_DIR.glob("*.part"),
        *RELATIONSHIP_UPLOAD_DIR.glob("*.chunk"),
        *RELATIONSHIP_UPLOAD_DIR.glob("*.result.json"),
        *RELATIONSHIP_UPLOAD_DIR.glob("*.writing"),
    ]
    for candidate in candidates:
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            continue


def _clear_relationship_chunks(upload_id: str) -> None:
    for candidate in RELATIONSHIP_UPLOAD_DIR.glob(f"{upload_id}.*.chunk"):
        candidate.unlink(missing_ok=True)


@router.get("", dependencies=[Depends(authorize_admin)])
def social_center(refresh: bool = Query(False)) -> dict[str, Any]:
    return social_dashboard(refresh=refresh)


@router.get("/media/{network}/{post_id}", dependencies=[Depends(authorize_admin)])
def social_post_media(network: str, post_id: str) -> Response:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,190}", post_id or ""):
        raise HTTPException(422, "Invalid social post identifier")
    try:
        content, content_type = social_media(network, post_id)
        return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=86400"})
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


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


@router.post("/audience-import-part", dependencies=[Depends(authorize_admin)])
async def social_audience_import_part(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    offset: int = Form(...),
    total_size: int = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Store one independently retryable part of a parallel browser upload."""
    if total_size < 1 or total_size > MAX_RELATIONSHIP_EXPORT_BYTES:
        raise HTTPException(413, "Choose a Meta export smaller than 512 MB")
    if total_chunks < 1 or total_chunks > 2048 or chunk_index < 0 or chunk_index >= total_chunks or offset < 0:
        raise HTTPException(422, "Invalid upload sequence; start the import again")
    data = await file.read(MAX_RELATIONSHIP_CHUNK_BYTES + 1)
    if not data or len(data) > MAX_RELATIONSHIP_CHUNK_BYTES or offset + len(data) > total_size:
        raise HTTPException(413, "An import piece was invalid; start the import again")
    _remove_stale_relationship_uploads()
    part_path = _relationship_chunk_path(upload_id, chunk_index)
    temporary_part = part_path.with_suffix(".writing")
    temporary_part.write_bytes(data)
    temporary_part.replace(part_path)
    return {"complete": False, "chunk_index": chunk_index, "received": len(data), "total": total_size}


@router.post("/audience-import-finalize", dependencies=[Depends(authorize_admin)])
async def social_audience_import_finalize(
    request: Request,
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    total_size: int = Form(...),
) -> dict[str, Any]:
    """Assemble verified parts once, then parse only relationship JSON members."""
    if total_size < 1 or total_size > MAX_RELATIONSHIP_EXPORT_BYTES or total_chunks < 1 or total_chunks > 2048:
        raise HTTPException(422, "Invalid upload; start the import again")
    base_path = _relationship_upload_path(upload_id)
    temporary_path = base_path.with_suffix(".assembled")
    result_path = RELATIONSHIP_UPLOAD_DIR / f"{upload_id}.result.json"
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            result_path.unlink(missing_ok=True)
    parts = [_relationship_chunk_path(upload_id, index) for index in range(total_chunks)]
    if any(not part.exists() for part in parts):
        raise HTTPException(409, "Some upload pieces did not arrive; please try the import again")
    try:
        with temporary_path.open("wb") as destination:
            for part in parts:
                with part.open("rb") as source:
                    while block := source.read(1024 * 1024):
                        destination.write(block)
        if temporary_path.stat().st_size != total_size:
            raise HTTPException(409, "The uploaded export was incomplete; please try the import again")
        username = (request.headers.get("X-Remote-User-Name") or "administrator").strip()
        result = json_ready(import_relationship_export_file(temporary_path, Path(filename).name, username))
        result["complete"] = True
        result_path.write_text(json.dumps(result), encoding="utf-8")
        return result
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(500, "Instagram relationship import failed: " + str(error)[:300]) from error
    finally:
        temporary_path.unlink(missing_ok=True)
        _clear_relationship_chunks(upload_id)
