"""Outbound-only synchronization for review-first mobile field intake."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import hmac
import json
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .config import runtime_option
from .db import connect, fetch_all, fetch_one, transaction
from .domains.attachments import MAX_ATTACHMENT_BYTES, store_attachment
from .remote_erp import _canonical, _decode_key, _safe_columns, reporting_row_revision
from .service import audit, estate_id, new_id


_lock = threading.Lock()
KINDS = {"field_observation", "damage_report", "work_report", "cellar_note", "agronomy_note", "enology_reading"}
ENTITY_TABLES = {
    "block_id": "vineyard_blocks", "task_id": "tasks", "work_activity_id": "work_activities",
    "container_id": "cellar_containers", "wine_lot_id": "wine_lots",
}
ENOLOGY_MEASUREMENTS = {
    "babo": "degree_babo", "temperature_c": "celsius", "density_sg": "specific_gravity",
    "brix": "degree_brix", "ph": "pH",
}
MEDIA_SIGNATURES = {
    "image/jpeg": lambda body: body.startswith(b"\xff\xd8\xff"),
    "image/png": lambda body: body.startswith(b"\x89PNG\r\n\x1a\n"),
    "application/pdf": lambda body: body.startswith(b"%PDF-"),
}


class IntakeRejected(ValueError):
    pass


class IntakeConflict(Exception):
    def __init__(self, reason: str, actual_revisions: dict[str, str], evidence_durable: bool = False):
        super().__init__(reason)
        self.actual_revisions = actual_revisions
        self.evidence_durable = evidence_durable


@dataclass(frozen=True)
class RemoteIntakeConfig:
    enabled: bool
    base_url: str
    key_id: str
    secret: str
    poll_seconds: int
    actor_roles: dict[str, str]

    @classmethod
    def current(cls) -> "RemoteIntakeConfig":
        configured_roles = runtime_option("remote_mobile_intake_actor_roles", {})
        if isinstance(configured_roles, str):
            try: configured_roles = json.loads(configured_roles)
            except json.JSONDecodeError: configured_roles = {}
        return cls(
            bool(runtime_option("remote_mobile_intake_enabled", False)),
            str(runtime_option("remote_erp_url", "https://cantinabaiamonte.com/erp")).rstrip("/"),
            str(runtime_option("remote_mobile_intake_key_id", "baiamonte-intake-1")).strip(),
            str(runtime_option("remote_mobile_intake_hmac_key", "")).strip(),
            max(5, min(60, int(runtime_option("remote_mobile_intake_poll_seconds", 10)))),
            {str(key).strip().casefold(): str(value).strip().casefold() for key, value in (configured_roles or {}).items()} if isinstance(configured_roles, dict) else {},
        )

    def validate(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Remote mobile intake URL must be HTTPS")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.key_id):
            raise ValueError("Remote mobile intake key ID is invalid")
        _decode_key(self.secret)
        if not self.actor_roles or any(not name or role not in {"operator", "admin"} for name, role in self.actor_roles.items()):
            raise ValueError("Remote mobile intake actor roles are not configured")


def _intake_signed_post(config: RemoteIntakeConfig, route: str, payload: dict[str, Any], timeout_seconds: int = 30, binary: bool = False) -> Any:
    config.validate()
    plain = _canonical(payload).encode(); body = gzip.compress(plain, compresslevel=6, mtime=0)
    timestamp = str(int(datetime.now(timezone.utc).timestamp())); nonce = secrets.token_urlsafe(32)
    path = "/erp" + route; body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(("POST", path, config.key_id, timestamp, nonce, body_hash))
    signature = hmac.new(config.secret.encode("ascii"), canonical.encode(), hashlib.sha256).hexdigest()
    request = Request(config.base_url + route, data=body, method="POST", headers={
        "Content-Type": "application/json", "Content-Encoding": "gzip", "X-Baiamonte-Uncompressed-Length": str(len(plain)),
        "X-Baiamonte-Key-Id": config.key_id, "X-Baiamonte-Timestamp": timestamp, "X-Baiamonte-Nonce": nonce,
        "X-Baiamonte-Signature": "sha256=" + signature,
    })
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            data = response.read(MAX_ATTACHMENT_BYTES + 1 if binary else 4 * 1024 * 1024)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise RuntimeError("mobile intake request failed") from error
    if binary: return data
    try: result = json.loads(data)
    except json.JSONDecodeError as error: raise RuntimeError("mobile intake response was invalid") from error
    if not isinstance(result, dict) or result.get("ok") is not True: raise RuntimeError("mobile intake request was rejected")
    return result


def _signed_attachment(config: RemoteIntakeConfig, attachment_uuid: str, payload: dict[str, Any]) -> bytes:
    data = _intake_signed_post(config, f"/sync/mobile-intake/attachments/{attachment_uuid}", payload, 30, True)
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise IntakeRejected("attachment_size_invalid")
    return data


def _validate_payload(item: dict[str, Any], config: RemoteIntakeConfig) -> tuple[dict[str, Any], dict[str, str]]:
    payload = item.get("payload")
    if not isinstance(payload, dict) or payload.get("contract") != "baiamonte.mobile-intake.v1":
        raise IntakeRejected("unsupported_contract")
    if str(payload.get("report_uuid") or "") != str(item.get("report_uuid") or ""):
        raise IntakeRejected("report_identity_mismatch")
    if payload.get("estate_id") != estate_id() or item.get("estate_id") != estate_id():
        raise IntakeRejected("estate_mismatch")
    kind = str(payload.get("kind") or "")
    if kind not in KINDS or kind != str(item.get("kind") or ""):
        raise IntakeRejected("unsupported_kind")
    actor = item.get("actor") or {}
    if actor.get("server_role") not in {"operator", "admin"} or not str(actor.get("username") or ""):
        raise IntakeRejected("actor_not_permitted")
    if payload.get("author") != actor:
        raise IntakeRejected("actor_binding_mismatch")
    expected_role = config.actor_roles.get(str(actor.get("username") or "").casefold())
    if expected_role != str(actor.get("server_role") or "").casefold():
        raise IntakeRejected("actor_authority_not_current")
    authority = item.get("authority") or {}
    try: checked_at = datetime.fromisoformat(str(authority.get("checked_at") or "").replace("Z", "+00:00"))
    except ValueError as error: raise IntakeRejected("authority_attestation_invalid") from error
    if authority.get("capability") != "intake.submit" or authority.get("session_active") is not True or abs((datetime.now(timezone.utc)-checked_at).total_seconds()) > 180:
        raise IntakeRejected("authority_attestation_invalid")
    entities = payload.get("entities")
    expected = payload.get("expected_revisions")
    if not isinstance(entities, dict) or not isinstance(expected, dict) or set(entities) != set(expected):
        raise IntakeRejected("entity_revision_contract_invalid")
    measurements = payload.get("measurements") or []
    if kind == "enology_reading":
        if not measurements:
            raise IntakeRejected("enology_measurement_required")
        for row in measurements:
            if not isinstance(row, dict) or ENOLOGY_MEASUREMENTS.get(str(row.get("code"))) != row.get("unit"):
                raise IntakeRejected("enology_measurement_invalid")
    return payload, {str(key): str(value) for key, value in expected.items()}


def _validate_revisions(payload: dict[str, Any], expected: dict[str, str]) -> dict[str, str]:
    entities = payload["entities"]
    actual: dict[str, str] = {}
    for key, record_id in entities.items():
        table = ENTITY_TABLES.get(str(key))
        if not table or not isinstance(record_id, str):
            raise IntakeRejected("unsupported_entity_reference")
        row = _reporting_entity(table, record_id)
        if not row:
            raise IntakeConflict("entity_not_found", actual)
        actual[str(key)] = str(reporting_row_revision(row))
    if any(actual.get(key) != revision for key, revision in expected.items()):
        raise IntakeConflict("expected_revision_conflict", actual)
    container_id, wine_lot_id = entities.get("container_id"), entities.get("wine_lot_id")
    if container_id and wine_lot_id:
        lot = _reporting_entity("wine_lots", wine_lot_id) or {}
        if str(lot.get("current_container_id") or "") != str(container_id):
            raise IntakeConflict("container_lot_assignment_conflict", actual)
    return actual


def _reporting_entity(table: str, record_id: str) -> dict[str, Any] | None:
    """Read exactly the columns used by the snapshot revision contract."""
    connection = connect()
    try:
        with connection.cursor() as cursor:
            columns = _safe_columns(cursor).get(table) or []
            if "id" not in columns or "estate_id" not in columns:
                raise IntakeRejected("entity_not_in_reporting_contract")
            cursor.execute(
                f"SELECT {','.join(f'`{column}`' for column in columns)} FROM `{table}` WHERE id=%s AND estate_id=%s",
                (record_id, estate_id()),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def _download_attachments(config: RemoteIntakeConfig, item: dict[str, Any], payload: dict[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    reserved = {str(row.get("sha256")): row for row in payload.get("attachments") or [] if isinstance(row, dict)}
    metadata = item.get("attachments") or []
    if len(metadata) != len(reserved):
        raise IntakeRejected("attachments_incomplete")
    stored: list[tuple[Any, dict[str, Any]]] = []
    try:
        for row in metadata:
            digest, media = str(row.get("file_sha256") or ""), str(row.get("media_type") or "")
            descriptor = reserved.get(digest)
            if not descriptor or media != descriptor.get("media_type") or int(row.get("byte_count") or 0) != int(descriptor.get("byte_count") or -1):
                raise IntakeRejected("attachment_descriptor_mismatch")
            data = _signed_attachment(config, str(row.get("attachment_uuid") or ""), {"report_uuid": item["report_uuid"], "lease_token": item["lease_token"]})
            if hashlib.sha256(data).hexdigest() != digest or len(data) != int(descriptor["byte_count"]) or not MEDIA_SIGNATURES[media](data):
                raise IntakeRejected("attachment_content_mismatch")
            attachment_id = new_id()
            stored.append((store_attachment(data, attachment_id, str(descriptor.get("filename") or ""), "mobile-intake"), {"id": attachment_id, **descriptor}))
        return stored
    except Exception:
        for file, _ in stored:
            file.discard()
        raise


def _stored_evidence_complete(report_uuid: str, payload: dict[str, Any]) -> bool:
    expected = {str(row.get("sha256")): row for row in payload.get("attachments") or [] if isinstance(row, dict)}
    if not expected:
        return True
    rows = fetch_all(
        "SELECT stored_path,media_type,file_sha256 FROM entity_attachments WHERE estate_id=%s AND entity_type='mobile_intake_draft' AND entity_id=%s",
        (estate_id(), report_uuid),
    )
    if len(rows) != len(expected):
        return False
    seen: set[str] = set()
    for row in rows:
        digest = str(row.get("file_sha256") or "")
        descriptor = expected.get(digest)
        path = str(row.get("stored_path") or "")
        if not descriptor or digest in seen or row.get("media_type") != descriptor.get("media_type") or not path:
            return False
        try:
            size = 0
            hasher = hashlib.sha256()
            with open(path, "rb") as handle:
                while chunk := handle.read(65536):
                    size += len(chunk)
                    if size > int(descriptor.get("byte_count") or -1):
                        return False
                    hasher.update(chunk)
        except OSError:
            return False
        if size != int(descriptor.get("byte_count") or -1) or hasher.hexdigest() != digest:
            return False
        seen.add(digest)
    return seen == set(expected)


def _store_draft(item: dict[str, Any], payload: dict[str, Any], payload_sha: str, stored: list[tuple[Any, dict[str, Any]]], ingest_status: str, reason: str | None, result: dict[str, Any]) -> None:
    correction = payload.get("correction_of_report_uuid")
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO mobile_intake_source_drafts(report_uuid,estate_id,actor_username,actor_role,entry_kind,occurred_at,received_at,source_timezone,payload_sha256,payload_json,correction_of_report_uuid,ingest_status,validation_reason,ingest_result_json,status,revision) VALUES(%s,%s,%s,%s,%s,%s,NOW(6),%s,%s,%s,%s,%s,%s,%s,'pending_review',1)",
                (item["report_uuid"], estate_id(), item["actor"]["username"], item["actor"]["server_role"], item["kind"],
                 datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00")).replace(tzinfo=None), payload["source_timezone"], payload_sha, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), correction, ingest_status, reason, json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
            )
            for file, descriptor in stored:
                cursor.execute(
                    "INSERT INTO entity_attachments(id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES(%s,%s,'mobile_intake_draft',%s,%s,%s,%s,%s,%s,%s)",
                    (descriptor["id"], estate_id(), item["report_uuid"], file.filename, str(file.path), descriptor["media_type"], file.sha256, "Mobile intake evidence", item["actor"]["username"]),
                )
            audit(cursor, "submit", "mobile_intake_draft", item["report_uuid"], {"kind": item["kind"], "payload_sha256": payload_sha, "attachments": len(stored), "ingest_status": ingest_status, "validation_reason": reason}, item["actor"]["username"])
    except Exception:
        for file, _ in stored: file.discard()
        raise


def _accept_report(config: RemoteIntakeConfig, item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    payload, expected = _validate_payload(item, config)
    payload_sha = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    existing = fetch_one("SELECT payload_sha256,ingest_status,ingest_result_json FROM mobile_intake_source_drafts WHERE report_uuid=%s", (item["report_uuid"],))
    if existing:
        if existing.get("payload_sha256") != payload_sha:
            raise IntakeConflict("source_uuid_collision", {})
        try: stored_result = json.loads(str(existing.get("ingest_result_json") or ""))
        except json.JSONDecodeError as error: raise RuntimeError("stored mobile intake result is invalid") from error
        ingest_status = str(existing.get("ingest_status") or "")
        if not isinstance(stored_result, dict) or ingest_status not in {"validated", "conflict", "rejected"}:
            raise RuntimeError("stored mobile intake result is invalid")
        if bool(stored_result.get("evidence_durable")) and not _stored_evidence_complete(str(item["report_uuid"]), payload):
            raise RuntimeError("stored mobile intake evidence is incomplete")
        return {"validated": "accepted", "conflict": "conflict", "rejected": "rejected"}[ingest_status], stored_result
    correction = payload.get("correction_of_report_uuid")
    if correction:
        original = fetch_one("SELECT estate_id,actor_username,entry_kind FROM mobile_intake_source_drafts WHERE report_uuid=%s", (correction,))
        if not original or original.get("estate_id") != estate_id() or str(original.get("actor_username") or "").casefold() != str(item["actor"]["username"]).casefold() or original.get("entry_kind") != item["kind"]:
            raise IntakeRejected("correction_reference_not_authorized")
    stored = _download_attachments(config, item, payload)
    try:
        actual = _validate_revisions(payload, expected)
    except IntakeConflict as error:
        result = {"authoritative_record_ids": [item["report_uuid"]], "actual_revisions": error.actual_revisions, "reason": str(error), "evidence_durable": True}
        _store_draft(item, payload, payload_sha, stored, "conflict", str(error), result)
        return "conflict", result
    except Exception:
        for file, _ in stored:
            file.discard()
        raise
    result = {"authoritative_record_ids": [item["report_uuid"]], "actual_revisions": actual, "reason": "pending_review", "evidence_durable": True}
    _store_draft(item, payload, payload_sha, stored, "validated", None, result)
    return "accepted", result


def process_mobile_intake_once(config: RemoteIntakeConfig | None = None) -> int:
    config = config or RemoteIntakeConfig.current()
    if not config.enabled:
        return 0
    config.validate()
    if not _lock.acquire(blocking=False):
        return 0
    try:
        response = _intake_signed_post(config, "/sync/mobile-intake/requests", {"limit": 10}, 30)
        handled = 0
        for item in response.get("reports", []):
            if not isinstance(item, dict):
                continue
            try:
                status, result = _accept_report(config, item)
            except IntakeConflict as error:
                result, status = {"authoritative_record_ids": [item.get("report_uuid")] if error.evidence_durable else [], "actual_revisions": error.actual_revisions, "reason": str(error), "evidence_durable": error.evidence_durable}, "conflict"
            except IntakeRejected as error:
                result, status = {"authoritative_record_ids": [], "actual_revisions": {}, "reason": str(error), "evidence_durable": False}, "rejected"
            _intake_signed_post(config, f"/sync/mobile-intake/results/{item.get('report_uuid', '')}", {"lease_token": item.get("lease_token"), "status": status, "result": result}, 30)
            handled += 1
        return handled
    finally:
        _lock.release()


async def remote_mobile_intake_loop() -> None:
    await asyncio.sleep(15)
    while True:
        config = RemoteIntakeConfig.current()
        if config.enabled:
            try:
                await asyncio.to_thread(process_mobile_intake_once, config)
            except Exception:
                # No payloads, keys or attachment details are logged.
                import logging
                logging.getLogger("baiamonte.mobile_intake").warning("Remote mobile intake poll failed", exc_info=True)
        await asyncio.sleep(config.poll_seconds if config.enabled else 60)
