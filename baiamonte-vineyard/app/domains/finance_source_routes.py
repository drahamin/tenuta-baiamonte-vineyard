from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from ..access import authorize_finance
from ..db import fetch_one
from ..fattureincloud import fresh_source_document_url
from ..service import estate_id


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/v1/finance/documents/{document_id}/original", dependencies=[Depends(authorize_finance)])
def open_finance_document_original(document_id: str) -> RedirectResponse:
    row = fetch_one(
        "SELECT document_type,source,external_source_id FROM financial_documents "
        "WHERE estate_id=%s AND id=%s",
        (estate_id(), document_id),
    )
    if not row:
        raise HTTPException(404, "Finance document not found")
    if row.get("source") != "fattureincloud" or not row.get("external_source_id"):
        raise HTTPException(404, "No Fatture in Cloud original is available")
    try:
        original = fresh_source_document_url(
            str(row["external_source_id"]), str(row.get("document_type") or "")
        )
    except Exception as error:
        logger.warning(
            "Unable to refresh Fatture in Cloud document %s: %s",
            document_id,
            type(error).__name__,
        )
        raise HTTPException(502, "Fatture in Cloud original is temporarily unavailable") from error
    if not original:
        raise HTTPException(404, "Fatture in Cloud did not provide an original document")
    return RedirectResponse(
        original,
        status_code=307,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )