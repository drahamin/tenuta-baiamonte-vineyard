from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal
from typing import Any

from .config import get_settings
from .db import fetch_one, transaction
from .service import estate_id, new_id


API_ROOT = "https://api-v2.fattureincloud.it"


def _get(path: str, parameters: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = API_ROOT + path + "?" + urllib.parse.urlencode(parameters)
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.fattureincloud_token}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read())


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _party(cursor: Any, item: dict[str, Any], party_type: str) -> str | None:
    entity = item.get("entity") or {}
    name = entity.get("name") or entity.get("company") or entity.get("first_name")
    if not name:
        return None
    cursor.execute("SELECT id FROM finance_parties WHERE estate_id=%s AND name=%s", (estate_id(), name))
    row = cursor.fetchone()
    if row:
        return row["id"]
    record_id = new_id()
    cursor.execute(
        "INSERT INTO finance_parties (id,estate_id,party_type,name,tax_code,vat_id,email,source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,'fattureincloud',%s)",
        (record_id, estate_id(), party_type, name, entity.get("tax_code"), entity.get("vat_number"), entity.get("email"), f"Fatture in Cloud entity {entity.get('id') or 'unknown'}"),
    )
    return record_id


def _payment_status(item: dict[str, Any]) -> str:
    payments = item.get("payments_list") or []
    if payments and all(payment.get("paid_date") or payment.get("status") == "paid" for payment in payments):
        return "paid"
    if any(payment.get("paid_date") or payment.get("status") == "paid" for payment in payments):
        return "part_paid"
    return "unpaid" if payments else "unknown"


def _upsert_document(cursor: Any, item: dict[str, Any], document_type: str, party_type: str) -> None:
    external_id = str(item.get("id") or "")
    if not external_id:
        return
    party_id = _party(cursor, item, party_type)
    net = _money(item.get("amount_net") or item.get("net_price"))
    vat = _money(item.get("amount_vat"))
    gross = _money(item.get("amount_gross") or item.get("gross_price"))
    if not gross:
        gross = net + vat
    number = str(item.get("number") or external_id)
    document_date = item.get("date") or date.today().isoformat()
    due_dates = [payment.get("due_date") for payment in item.get("payments_list") or [] if payment.get("due_date")]
    due_date = min(due_dates) if due_dates else None
    status = "paid" if _payment_status(item) == "paid" else ("issued" if document_type == "sales_invoice" else "received")
    cursor.execute("SELECT id FROM financial_documents WHERE estate_id=%s AND source='fattureincloud' AND external_source_id=%s", (estate_id(), external_id))
    existing = cursor.fetchone()
    record_id = existing["id"] if existing else new_id()
    cursor.execute(
        "INSERT INTO financial_documents (id,estate_id,document_type,document_number,document_date,due_date,party_id,currency,taxable_amount,vat_amount,gross_total,status,payment_status,source,source_document,external_source_id,notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'fattureincloud',%s,%s,'Read-only mirror from Fatture in Cloud') "
        "ON DUPLICATE KEY UPDATE due_date=VALUES(due_date),party_id=VALUES(party_id),currency=VALUES(currency),taxable_amount=VALUES(taxable_amount),vat_amount=VALUES(vat_amount),gross_total=VALUES(gross_total),status=VALUES(status),payment_status=VALUES(payment_status),source='fattureincloud',source_document=VALUES(source_document),external_source_id=VALUES(external_source_id),updated_at=NOW()",
        (record_id, estate_id(), document_type, number, document_date, due_date, party_id, item.get("currency", {}).get("id") or "EUR", net, vat, gross, status, _payment_status(item), item.get("url") or item.get("attachment_url"), external_id),
    )


def pull_fattureincloud() -> dict[str, Any]:
    settings = get_settings()
    if not settings.fattureincloud_token or not settings.fattureincloud_company_id:
        return {"configured": False, "message": "Add the Fatture in Cloud manual token and company ID in app configuration."}
    counts = {"sales_invoices": 0, "purchase_invoices": 0, "credit_notes": 0, "delivery_notes": 0}
    company = urllib.parse.quote(settings.fattureincloud_company_id, safe="")
    start_year = date.today().year - max(1, settings.fattureincloud_sync_years) + 1
    streams = (("issued_documents", "invoice", "sales_invoice", "customer", "sales_invoices"), ("issued_documents", "credit_note", "credit_note", "customer", "credit_notes"), ("issued_documents", "delivery_note", "delivery_note", "customer", "delivery_notes"), ("received_documents", "expense", "purchase_invoice", "supplier", "purchase_invoices"))
    with transaction() as (_, cursor):
        for resource, source_type, document_type, party_type, counter in streams:
            for year in range(start_year, date.today().year + 1):
                page = 1
                while True:
                    payload = _get(f"/c/{company}/{resource}", {"type": source_type, "year": year, "page": page, "per_page": 100, "fieldset": "detailed"})
                    rows = payload.get("data") or []
                    for item in rows:
                        _upsert_document(cursor, item, document_type, party_type)
                        counts[counter] += 1
                    if not rows or page >= int((payload.get("meta") or {}).get("pagination", {}).get("page_count") or page):
                        break
                    page += 1
        cursor.execute("INSERT INTO sync_checkpoints (estate_id,integration_name,last_success_at,last_attempt_at,metadata) VALUES (%s,'fattureincloud',NOW(),NOW(),%s) ON DUPLICATE KEY UPDATE last_success_at=NOW(),last_attempt_at=NOW(),last_error=NULL,metadata=VALUES(metadata)", (estate_id(), json.dumps(counts)))
    return {"configured": True, "read_only": True, "counts": counts}
