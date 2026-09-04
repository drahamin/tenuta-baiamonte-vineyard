"""Admin-only official record registry and durable PDF storage."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ..access import authorize_admin
from ..db import fetch_all, fetch_one, transaction
from ..service import estate_id
from .attachments import ATTACHMENT_ROOT, MAX_ATTACHMENT_BYTES, store_attachment


router = APIRouter(prefix="/official-documents", tags=["official documents"])
DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
ALLOWED_TYPES = {
    "cadastral_record", "vineyard_register", "harvest_declaration",
    "company_register", "company_formation", "permit", "contract", "other",
}


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def official_document_rows() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,"
        "original_filename,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope,"
        "supersedes_document_id,created_at,updated_at FROM official_documents WHERE estate_id=%s "
        "ORDER BY FIELD(status,'current','reference','historical','superseded','draft'),COALESCE(issue_date,'0001-01-01') DESC,title",
        (estate_id(),),
    )
    for row in rows:
        row["verified_facts"] = _json_value(row.get("verified_facts"), {})
        row["related_scope"] = _json_value(row.get("related_scope"), {})
        row["view_url"] = f"api/v1/admin/official-documents/{row['id']}/file"
        row["download_url"] = f"api/v1/admin/official-documents/{row['id']}/file?download=true"
    return rows


def atlas_official_sources() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in official_document_rows():
        scope = row.get("related_scope") or {}
        for parcel in scope.get("parcels") or []:
            result.setdefault(str(parcel), []).append({
                "id": row["id"], "title": row["title"], "issue_date": row.get("issue_date"),
                "status": row["status"], "summary": row.get("summary"), "view_url": row["view_url"],
            })
    return result


def _document_path(row: dict[str, Any]) -> Path:
    root = DOCS_ROOT if row.get("storage_kind") == "bundled" else ATTACHMENT_ROOT
    path = (root / str(row.get("stored_path") or "")).resolve()
    if root.resolve() not in path.parents:
        raise HTTPException(404, "Official document is unavailable")
    if not path.is_file():
        raise HTTPException(404, "Official document file is missing")
    return path


@router.get("", dependencies=[Depends(authorize_admin)])
def list_official_documents() -> dict[str, Any]:
    rows = official_document_rows()
    return {
        "documents": rows,
        "counts": {
            "total": len(rows),
            "current": sum(row["status"] == "current" for row in rows),
            "reference": sum(row["status"] == "reference" for row in rows),
            "historical": sum(row["status"] in {"historical", "superseded"} for row in rows),
            "atlas_linked": sum("atlas" in (row.get("related_scope") or {}).get("domains", []) for row in rows),
        },
        "policy": "Original PDFs are retained unchanged. Verified facts are dated and never overwrite a conflicting record silently.",
    }


@router.get("/{document_id}/file", dependencies=[Depends(authorize_admin)])
def official_document_file(document_id: str, download: bool = Query(False)):
    row = fetch_one(
        "SELECT storage_kind,stored_path,original_filename,mime_type FROM official_documents WHERE id=%s AND estate_id=%s",
        (document_id, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Official document not found")
    path = _document_path(row)
    disposition = "attachment" if download else "inline"
    safe_name = re.sub(r'[\r\n"]+', "_", str(row["original_filename"]))
    return FileResponse(path, media_type=row.get("mime_type") or "application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="{safe_name}"',
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("", dependencies=[Depends(authorize_admin)])
async def upload_official_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form("other"),
    issuing_authority: str = Form(""),
    reference_number: str = Form(""),
    issue_date: date | None = Form(None),
    effective_year: int | None = Form(None),
    summary: str = Form(""),
) -> dict[str, Any]:
    if document_type not in ALLOWED_TYPES:
        raise HTTPException(422, "Unsupported official document type")
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "Official PDF must be between 1 byte and 15 MB")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Only genuine PDF documents are accepted")
    digest = hashlib.sha256(data).hexdigest()
    existing = fetch_one("SELECT id FROM official_documents WHERE estate_id=%s AND file_sha256=%s", (estate_id(), digest))
    if existing:
        raise HTTPException(409, "This exact official document is already registered")
    document_id = str(uuid.uuid4())
    stored = store_attachment(data, document_id, file.filename or "official-document.pdf", "official-document.pdf")
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO official_documents (id,estate_id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,original_filename,storage_kind,stored_path,mime_type,file_sha256,file_size,page_count,summary,verified_facts,related_scope) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,'uploaded',%s,'application/pdf',%s,%s,NULL,%s,JSON_OBJECT(),JSON_OBJECT('domains',JSON_ARRAY()))",
                (document_id, estate_id(), document_type, title.strip(), issuing_authority.strip() or None,
                 reference_number.strip() or None, issue_date, effective_year, stored.filename, stored.path.name,
                 stored.sha256, len(data), summary.strip() or None),
            )
    except Exception:
        stored.discard()
        raise
    return {"id": document_id, "status": "draft", "message": "Official PDF retained; verify its facts and links before marking current."}
