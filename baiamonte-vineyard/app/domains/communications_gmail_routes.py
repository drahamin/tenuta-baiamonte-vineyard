"""Gmail communications routes with stable public API contracts."""

from __future__ import annotations

import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile

from ..access import authorize, authorize_write
from ..db import transaction
from ..intelligence import send_gmail_message
from ..mailbox import gmail_download, gmail_folders, gmail_message, gmail_message_action, gmail_messages
from ..service import audit, json_ready


router = APIRouter(prefix="/api/v1/communications/gmail", tags=["communications"])


@router.get("/folders", dependencies=[Depends(authorize)])
def communication_gmail_folders(refresh: bool = False) -> dict[str, Any]:
    try:
        return {"folders": gmail_folders(refresh=refresh)}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail folders failed: " + str(error)[:300]) from error


@router.get("/messages", dependencies=[Depends(authorize)])
def communication_gmail_messages(
    folder: str = "INBOX", view: str = "all", limit: int = 50, refresh: bool = False,
) -> dict[str, Any]:
    try:
        return json_ready(gmail_messages(folder, view, limit, refresh=refresh))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail mailbox failed: " + str(error)[:300]) from error


@router.get("/messages/{uid}", dependencies=[Depends(authorize)])
def communication_gmail_message(uid: str, folder: str = "INBOX") -> dict[str, Any]:
    try:
        return json_ready(gmail_message(uid, folder))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail message failed: " + str(error)[:300]) from error


def _download_response(data: bytes, filename: str, content_type: str) -> Response:
    disposition = f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"
    return Response(data, media_type=content_type, headers={"Content-Disposition": disposition})


@router.get("/messages/{uid}/download", dependencies=[Depends(authorize)])
def communication_gmail_download(uid: str, folder: str = "INBOX") -> Response:
    try:
        return _download_response(*gmail_download(uid, folder))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail download failed: " + str(error)[:300]) from error


@router.get("/messages/{uid}/attachments/{attachment_index}", dependencies=[Depends(authorize)])
def communication_gmail_attachment(uid: str, attachment_index: int, folder: str = "INBOX") -> Response:
    try:
        return _download_response(*gmail_download(uid, folder, attachment_index))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail attachment failed: " + str(error)[:300]) from error


@router.patch("/messages/{uid}", dependencies=[Depends(authorize_write)])
def communication_gmail_action(uid: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        folder = str(payload.get("folder") or "INBOX")
        result = gmail_message_action(uid, str(payload.get("action") or ""), folder)
        with transaction() as (_, cursor):
            audit(
                cursor,
                "gmail_message_action",
                "gmail_message",
                uid,
                {"action": result["action"], "folder": folder},
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return result
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail action failed: " + str(error)[:300]) from error


@router.post("/send", dependencies=[Depends(authorize_write)])
def communication_send_gmail(payload: dict[str, Any]) -> dict[str, Any]:
    recipients = payload.get("recipients") or []
    if isinstance(recipients, str):
        recipients = [item.strip() for item in recipients.split(",") if item.strip()]
    try:
        return send_gmail_message(recipients, str(payload.get("subject") or ""), str(payload.get("body") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail send failed: " + str(error)[:300]) from error


@router.post("/send-files", dependencies=[Depends(authorize_write)])
async def communication_send_gmail_files(
    recipients: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    try:
        attachments = []
        total_bytes = 0
        for file in files[:10]:
            data = await file.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Each attachment must be 20 MB or smaller")
            total_bytes += len(data)
            if total_bytes > 30 * 1024 * 1024:
                raise ValueError("The combined attachments must be 30 MB or smaller")
            if data:
                attachments.append((file.filename or "attachment", file.content_type or "application/octet-stream", data))
        recipient_list = [value.strip() for value in recipients.split(",")]
        return send_gmail_message(recipient_list, subject, body, attachments)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail send failed: " + str(error)[:300]) from error
