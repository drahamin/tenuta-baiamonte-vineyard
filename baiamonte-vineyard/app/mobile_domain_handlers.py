"""Source-disabled authoritative handlers for mobile timeclock and cellar actions.

Nothing imports this module from the running application.  Activation requires
the proposed schema, explicit worker wiring and dedicated capability approval.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .db import transaction
from .remote_erp import _canonical, _safe_columns, reporting_row_revision
from .service import audit, estate_id, new_id


HANDLERS = {"timeclock": "vineyard.timeclock.record_event.v1", "cellar": "vineyard.cellar.apply_operation.v1"}
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


class DomainRejected(ValueError):
    pass


class DomainConflict(Exception):
    def __init__(self, reason: str, revisions: dict[str, str] | None = None):
        super().__init__(reason); self.revisions = revisions or {}


@dataclass(frozen=True)
class HandlerOutcome:
    status: str
    result: dict[str, Any]


def handle_mobile_domain_action(item: dict[str, Any]) -> HandlerOutcome:
    """Apply one validated lease exactly once inside an authoritative transaction."""
    workflow = str(item.get("workflow") or "")
    action_uuid = _uuid(item.get("action_uuid"), "action_uuid")
    if item.get("contract") != "baiamonte.mobile-pending-domain.v1" or item.get("authoritative_handler") != HANDLERS.get(workflow):
        raise DomainRejected("unsupported_handler_contract")
    if item.get("estate_id") != estate_id():
        raise DomainRejected("estate_mismatch")
    actor = item.get("actor")
    payload = item.get("payload")
    if not isinstance(actor, dict) or not isinstance(payload, dict) or payload.get("estate_id") != estate_id():
        raise DomainRejected("actor_or_payload_invalid")
    if payload.get("actor", {}).get("username") != actor.get("username") or payload.get("actor", {}).get("server_role") != actor.get("server_role"):
        raise DomainRejected("actor_binding_mismatch")
    payload_sha = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    with transaction() as (_, cursor):
        cursor.execute("SELECT workflow,payload_sha256,status,result_json FROM mobile_domain_action_receipts WHERE action_uuid=%s FOR UPDATE", (action_uuid,))
        prior = cursor.fetchone()
        if prior:
            if prior.get("workflow") != workflow or prior.get("payload_sha256") != payload_sha:
                raise DomainConflict("source_uuid_collision")
            if prior.get("status") not in {"accepted", "rejected", "conflict"}:
                raise RuntimeError("mobile domain receipt is incomplete")
            stored = json.loads(str(prior.get("result_json") or "{}"))
            if not isinstance(stored, dict):
                raise RuntimeError("mobile domain receipt is invalid")
            return HandlerOutcome(str(prior["status"]), stored)
        cursor.execute(
            "INSERT INTO mobile_domain_action_receipts(action_uuid,estate_id,workflow,payload_sha256,status,result_json) VALUES(%s,%s,%s,%s,'processing',JSON_OBJECT())",
            (action_uuid, estate_id(), workflow, payload_sha),
        )
        try:
            result = _record_timeclock(cursor, action_uuid, payload, actor) if workflow == "timeclock" else _apply_cellar(cursor, action_uuid, payload, actor)
            status = "accepted"
        except DomainConflict as error:
            status = "conflict"
            result = _result([], error.revisions, str(error), None, False, False)
        except DomainRejected as error:
            status = "rejected"
            result = _result([], {}, str(error), None, False, False)
        cursor.execute(
            "UPDATE mobile_domain_action_receipts SET status=%s,result_json=%s,resolved_at=NOW(6) WHERE action_uuid=%s AND status='processing'",
            (status, json.dumps(result, ensure_ascii=False, separators=(",", ":")), action_uuid),
        )
        audit(cursor, "mobile_domain_result", "mobile_domain_action", action_uuid, {"workflow": workflow, "status": status, "result": result}, str(actor.get("username") or "mobile"))
        return HandlerOutcome(status, result)


def _record_timeclock(cursor: Any, action_uuid: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract") != "baiamonte.mobile-timeclock.v1":
        raise DomainRejected("unsupported_timeclock_contract")
    if payload.get("correction_of_event_uuid") is not None:
        raise DomainRejected("timeclock_correction_requires_supervisor_review")
    event_uuid = _uuid(payload.get("event_uuid"), "event_uuid")
    if event_uuid != action_uuid:
        raise DomainRejected("timeclock_identity_mismatch")
    shift_uuid = _uuid(payload.get("shift_uuid"), "shift_uuid")
    person_id = str(payload.get("actor", {}).get("person_id") or "")
    username = str(actor.get("username") or "")
    cursor.execute("SELECT id,name,role FROM people WHERE id=%s AND estate_id=%s AND active=1 AND is_worker=1 FOR UPDATE", (person_id, estate_id()))
    person = cursor.fetchone()
    if not person:
        raise DomainRejected("worker_binding_not_found")
    cursor.execute("SELECT event_type,occurred_at,shift_revision FROM mobile_timeclock_events WHERE estate_id=%s AND shift_uuid=%s ORDER BY shift_revision FOR UPDATE", (estate_id(), shift_uuid))
    events = list(cursor.fetchall() or [])
    current_revision = str(events[-1]["shift_revision"]) if events else None
    expected = payload.get("expected_shift_revision")
    if expected != current_revision:
        raise DomainConflict("expected_shift_revision_conflict", {"shift_uuid": current_revision or "0"})
    event_type = str(payload.get("event_type") or "")
    latest = str(events[-1]["event_type"]) if events else None
    allowed = {None: {"clock_in"}, "clock_in": {"break_start", "clock_out"}, "break_start": {"break_end"}, "break_end": {"break_start", "clock_out"}}
    if event_type not in allowed.get(latest, set()):
        raise DomainConflict("invalid_timeclock_transition", {"shift_uuid": current_revision or "0"})
    occurred = _occurred(payload.get("occurred_at"))
    revision = len(events) + 1
    if event_type == "clock_in":
        cursor.execute("SELECT id FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft' LIMIT 1 FOR UPDATE", (estate_id(), username))
        if cursor.fetchone():
            raise DomainConflict("worker_already_clocked_in")
        cursor.execute("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s LIMIT 1", (estate_id(), occurred.year))
        season = cursor.fetchone() or {}
        cursor.execute(
            "INSERT INTO labor_entries(id,estate_id,season_id,person_id,source_labor_id,work_date,person_or_crew,role,start_time,regular_hours,overtime_hours,payroll_scope,payment_status,entry_source,worker_username,clock_in_at,approval_status,work_category,work_performed) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,'unknown','verification_needed','mobile_timeclock',%s,%s,'draft','general',%s)",
            (shift_uuid, estate_id(), season.get("id"), person_id, "mobile:" + event_uuid, occurred.date(), person["name"], person.get("role"), occurred.time(), username, occurred, payload.get("note")),
        )
    elif event_type == "clock_out":
        started = _event_time(events[0].get("occurred_at"))
        if occurred <= started:
            raise DomainConflict("clock_out_not_after_clock_in", {"shift_uuid": current_revision or "0"})
        break_seconds = _break_seconds(events, occurred)
        hours = Decimal(str(round(max(0, (occurred - started).total_seconds() - break_seconds) / 3600, 2)))
        cursor.execute("UPDATE labor_entries SET clock_out_at=%s,end_time=%s,regular_hours=%s,approval_status='submitted',submitted_at=%s WHERE id=%s AND estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft'", (occurred, occurred.time(), hours, occurred, shift_uuid, estate_id(), username))
        if cursor.rowcount != 1:
            raise DomainConflict("open_shift_not_found", {"shift_uuid": current_revision or "0"})
    cursor.execute("INSERT INTO mobile_timeclock_events(event_uuid,estate_id,shift_uuid,person_id,actor_username,event_type,occurred_at,shift_revision,payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (event_uuid, estate_id(), shift_uuid, person_id, username, event_type, occurred, revision, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))
    return _result([event_uuid, shift_uuid], {"shift_uuid": str(revision)}, "pending_payroll_review" if event_type == "clock_out" else "recorded", None, False, False)


def _apply_cellar(cursor: Any, action_uuid: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract") != "baiamonte.mobile-cellar-operation.v1" or payload.get("operation_uuid") != action_uuid or actor.get("server_role") != "admin":
        raise DomainRejected("cellar_contract_or_authority_invalid")
    if payload.get("correction_of_operation_uuid") is not None:
        raise DomainRejected("cellar_correction_requires_review")
    kind = str(payload.get("kind") or "")
    values = payload.get("payload") or {}
    expected = payload.get("expected_revisions") or {}
    if kind not in {"racking.v1", "product_addition.v1", "filtration.v1", "tank_work.v1"} or not isinstance(values, dict) or not isinstance(expected, dict):
        raise DomainRejected("unsupported_cellar_operation")
    required_references = {
        "racking.v1": {"source_container_id", "target_container_id", "wine_lot_id"},
        "product_addition.v1": {"container_id", "wine_lot_id", "product_id"},
        "filtration.v1": {"container_id", "wine_lot_id"},
        "tank_work.v1": {"container_id", "wine_lot_id"},
    }[kind]
    if set(expected) != required_references or any(not isinstance(values.get(key), str) for key in required_references):
        raise DomainRejected("cellar_references_invalid")
    rows: dict[str, dict[str, Any]] = {}
    for key, revision in expected.items():
        table = {"source_container_id": "cellar_containers", "target_container_id": "cellar_containers", "container_id": "cellar_containers", "wine_lot_id": "wine_lots", "product_id": "products"}.get(str(key))
        record_id = values.get(key)
        if not table or not isinstance(record_id, str):
            raise DomainRejected("unsupported_cellar_reference")
        row, actual = _locked_reporting(cursor, table, record_id)
        if not row:
            raise DomainConflict("cellar_entity_not_found")
        if str(revision) != str(actual):
            raise DomainConflict("expected_revision_conflict", {str(key): str(actual)})
        rows[str(key)] = row
    lot = rows.get("wine_lot_id") or {}
    occurred = _occurred(payload.get("occurred_at"))
    transaction_uuid = new_id()
    operation_id = action_uuid
    if kind == "racking.v1":
        source, target = rows["source_container_id"], rows["target_container_id"]
        volume, loss = _number(values.get("transfer_volume_l")), _number(values.get("expected_loss_l"), allow_zero=True)
        recorded_volume = Decimal(str(lot.get("volume_l") or 0))
        cursor.execute("SELECT id FROM wine_lots WHERE estate_id=%s AND current_container_id=%s AND id<>%s LIMIT 1 FOR UPDATE", (estate_id(), target["id"], lot["id"]))
        target_occupied = cursor.fetchone()
        if lot.get("current_container_id") != source.get("id") or abs(volume - recorded_volume) > Decimal("0.001") or volume - loss > Decimal(str(target.get("capacity_l") or 0)) or target_occupied:
            raise DomainConflict("racking_assignment_capacity_or_volume_conflict")
        remaining = recorded_volume - loss
        cursor.execute("UPDATE wine_lots SET current_container_id=%s,volume_l=%s WHERE id=%s AND estate_id=%s", (target["id"], remaining, lot["id"], estate_id()))
        op_type, amount, unit, container, product = "racking", volume, "litre", target["id"], None
    elif kind == "product_addition.v1":
        container, product = rows["container_id"], rows["product_id"]
        quantity = _number(values.get("quantity")); unit = str(values.get("unit") or "")
        if lot.get("current_container_id") != container.get("id") or not product.get("active") or str(product.get("unit") or "") != unit:
            raise DomainConflict("product_or_container_assignment_conflict")
        cursor.execute("SELECT COALESCE(SUM(quantity_delta),0) quantity FROM inventory_movements WHERE estate_id=%s AND product_id=%s FOR UPDATE", (estate_id(), product["id"]))
        available = Decimal(str((cursor.fetchone() or {}).get("quantity") or 0))
        if quantity > available:
            raise DomainConflict("product_inventory_insufficient")
        movement_id = new_id()
        cursor.execute("INSERT INTO inventory_movements(id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes) VALUES(%s,%s,%s,%s,'use',%s,'cellar_operation',%s,%s)", (movement_id, estate_id(), product["id"], occurred, -quantity, operation_id, values.get("reason")))
        op_type, amount, container, product = "product_addition", quantity, container["id"], product["id"]
    elif kind == "filtration.v1":
        container = rows["container_id"]
        volume, loss = _number(values.get("processed_volume_l")), _number(values.get("expected_loss_l"), allow_zero=True)
        if lot.get("current_container_id") != container.get("id") or volume > Decimal(str(lot.get("volume_l") or 0)):
            raise DomainConflict("filtration_assignment_or_volume_conflict")
        cursor.execute("UPDATE wine_lots SET volume_l=%s WHERE id=%s AND estate_id=%s", (Decimal(str(lot.get("volume_l") or 0)) - loss, lot["id"], estate_id()))
        op_type, amount, unit, container, product = "filtration:" + str(values.get("method")), volume, "litre", container["id"], None
    else:
        container = rows["container_id"]
        if lot.get("current_container_id") != container.get("id"):
            raise DomainConflict("tank_work_assignment_conflict")
        op_type, amount, unit, container, product = "tank_work:" + str(values.get("operation")), values.get("duration_minutes"), "minute" if values.get("duration_minutes") else None, container["id"], None
    cursor.execute("INSERT INTO cellar_operations(id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,product_id,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (operation_id, estate_id(), lot.get("season_id"), lot.get("id"), container, occurred, op_type, amount, unit, product, values.get("note") or values.get("reason")))
    revisions = {}
    tables = {"source_container_id": "cellar_containers", "target_container_id": "cellar_containers", "container_id": "cellar_containers", "wine_lot_id": "wine_lots", "product_id": "products"}
    for key in rows:
        refreshed, actual = _locked_reporting(cursor, tables[key], str(values[key]))
        if not refreshed:
            raise RuntimeError("authoritative cellar row disappeared during transaction")
        revisions[key] = str(actual)
    return _result([operation_id], revisions, "applied", transaction_uuid, True, True)


def _locked_reporting(cursor: Any, table: str, record_id: str) -> tuple[dict[str, Any] | None, int]:
    columns = (_safe_columns(cursor).get(table) or [])
    if "id" not in columns or "estate_id" not in columns:
        raise DomainRejected("entity_not_in_reporting_contract")
    cursor.execute(f"SELECT {','.join(f'`{column}`' for column in columns)} FROM `{table}` WHERE id=%s AND estate_id=%s FOR UPDATE", (record_id, estate_id()))
    row = cursor.fetchone()
    return (row, reporting_row_revision(row)) if row else (None, 0)


def _result(ids: list[str], revisions: dict[str, str], reason: str, transaction_uuid: str | None, inventory: bool, atomic: bool) -> dict[str, Any]:
    return {"authoritative_record_ids": ids, "actual_revisions": revisions, "reason": reason, "transaction_uuid": transaction_uuid, "inventory_committed": inventory, "atomic": atomic}


def _uuid(value: Any, field: str) -> str:
    text = str(value or "").lower()
    if not UUID4.fullmatch(text):
        raise DomainRejected(f"{field}_invalid")
    return text


def _occurred(value: Any) -> datetime:
    try: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error: raise DomainRejected("occurred_at_invalid") from error
    if parsed.tzinfo is None:
        raise DomainRejected("occurred_at_invalid")
    return parsed.astimezone(ZoneInfo("Europe/Rome")).replace(tzinfo=None)


def _event_time(value: Any) -> datetime:
    if isinstance(value, datetime): return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value)).replace(tzinfo=None)


def _break_seconds(events: list[dict[str, Any]], ended: datetime) -> int:
    started: datetime | None = None; total = 0
    for event in events:
        kind, occurred = str(event.get("event_type")), _event_time(event.get("occurred_at"))
        if kind == "break_start": started = occurred
        elif kind == "break_end" and started is not None: total += max(0, int((occurred - started).total_seconds())); started = None
    if started is not None: total += max(0, int((ended - started).total_seconds()))
    return total


def _number(value: Any, allow_zero: bool = False) -> Decimal:
    try: number = Decimal(str(value))
    except Exception as error: raise DomainRejected("numeric_value_invalid") from error
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise DomainRejected("numeric_value_invalid")
    return number
