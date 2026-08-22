from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException

from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id


CENT = Decimal("0.01")
THREE = Decimal("0.001")
REGISTER_DEFAULTS = {
    "store_name": "Azienda Agricola Tenuta Baiamonte S.S.",
    "receipt_header": "Tenuta Baiamonte",
    "receipt_footer": "Grazie · Thank you",
    "receipt_note": "Operational receipt · not a fiscal document",
    "default_vat_rate": 22,
    "usd_per_eur": 1.1567,
    "exchange_rate_date": "2026-08-14",
    "exchange_rate_source": "ECB reference rate; editable checkout rate",
    "allow_cash": True,
    "allow_paypal_pos": True,
    "fic_sales_posting_enabled": False,
}


def _decimal(value: Any, name: str, minimum: Decimal = Decimal("0"), maximum: Decimal = Decimal("1000000")) -> Decimal:
    try:
        number = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(422, f"{name} must be a number") from error
    if not number.is_finite() or number < minimum or number > maximum:
        raise HTTPException(422, f"{name} is outside the allowed range")
    return number


def _money(value: Any) -> Decimal:
    return _decimal(value, "Amount").quantize(CENT, rounding=ROUND_HALF_UP)


def register_settings() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='register_settings'",
        (estate_id(),),
    ) or {}
    try:
        saved = json.loads(row.get("setting_value") or "{}")
    except (TypeError, json.JSONDecodeError):
        saved = {}
    result = {**REGISTER_DEFAULTS, **(saved if isinstance(saved, dict) else {})}
    if isinstance(saved, dict) and "allow_paypal_pos" not in saved and "allow_manual_card" in saved:
        result["allow_paypal_pos"] = bool(saved["allow_manual_card"])
    # The posting adapter is deliberately prepared but cannot be enabled from
    # the UI in this release. Local monthly ledger rows remain authoritative.
    result["fic_sales_posting_enabled"] = False
    return result


def save_register_settings(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    current = register_settings()
    for name in ("store_name", "receipt_header", "receipt_footer", "receipt_note"):
        if name in payload:
            current[name] = str(payload.get(name) or "").strip()[:500]
    if "default_vat_rate" in payload:
        current["default_vat_rate"] = float(_decimal(payload.get("default_vat_rate"), "VAT rate", Decimal("0"), Decimal("100")))
    if "usd_per_eur" in payload:
        current["usd_per_eur"] = float(_decimal(payload.get("usd_per_eur"), "USD per EUR", Decimal("0.1"), Decimal("10")))
        current["exchange_rate_date"] = date.today().isoformat()
        current["exchange_rate_source"] = "Administrator checkout rate"
    for name in ("allow_cash", "allow_paypal_pos"):
        if name in payload:
            current[name] = bool(payload[name])
    current["fic_sales_posting_enabled"] = False
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'register_settings',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(current, ensure_ascii=False)),
        )
        audit(cursor, "update", "register_settings", estate_id(), current, actor)
    return current


def refresh_exchange_rate(actor: str) -> dict[str, Any]:
    """Refresh the informational checkout rate from the free ECB daily feed."""
    try:
        request = urllib.request.Request(
            "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
            headers={"User-Agent": "Tenuta-Baiamonte-Register/1.6"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            root = ET.fromstring(response.read())
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
        raise HTTPException(502, "The ECB exchange-rate feed is temporarily unavailable") from error
    day = next((node.attrib.get("time") for node in root.iter() if node.attrib.get("time")), None)
    rate = next((node.attrib.get("rate") for node in root.iter() if node.attrib.get("currency") == "USD"), None)
    if not day or not rate:
        raise HTTPException(502, "The ECB feed did not contain a USD reference rate")
    current = register_settings()
    current["usd_per_eur"] = float(_decimal(rate, "ECB USD rate", Decimal("0.1"), Decimal("10")))
    current["exchange_rate_date"] = day
    current["exchange_rate_source"] = "European Central Bank reference rate"
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'register_settings',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(current, ensure_ascii=False)),
        )
        audit(cursor, "refresh_exchange_rate", "register_settings", estate_id(), {"USD": rate, "date": day}, actor)
    return current


def sync_hospitality_catalog() -> int:
    """Mirror active local hospitality packages into the register catalog."""
    packages = fetch_all(
        "SELECT id,name,description,experience_type,price_basis,price_eur,active,sort_order "
        "FROM hospitality_packages WHERE estate_id=%s",
        (estate_id(),),
    )
    with transaction() as (_, cursor):
        for package in packages:
            cursor.execute(
                "SELECT id FROM register_catalog_items WHERE estate_id=%s AND source_type='hospitality' AND external_id=%s",
                (estate_id(), package["id"]),
            )
            existing = cursor.fetchone()
            item_id = existing["id"] if existing else new_id()
            cursor.execute(
                "INSERT INTO register_catalog_items "
                "(id,estate_id,source_type,external_id,name,description,category,unit,gross_price_eur,net_price_eur,vat_rate,track_stock,sellable,price_editable,display_order,source_payload) "
                "VALUES (%s,%s,'hospitality',%s,%s,%s,%s,%s,%s,%s,0,0,%s,1,%s,%s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description),category=VALUES(category),unit=VALUES(unit),"
                "gross_price_eur=VALUES(gross_price_eur),net_price_eur=VALUES(net_price_eur),sellable=VALUES(sellable),price_editable=1,display_order=VALUES(display_order),source_payload=VALUES(source_payload)",
                (
                    item_id, estate_id(), package["id"], package["name"], package.get("description"),
                    package.get("experience_type") or "hospitality",
                    "guest" if package.get("price_basis") == "per_person" else "experience",
                    package.get("price_eur") or 0, package.get("price_eur") or 0,
                    1 if package.get("active") else 0, package.get("sort_order") or 100,
                    json.dumps(package, default=str, ensure_ascii=False),
                ),
            )
    return len(packages)


def _catalog_rows(include_hidden: bool = False) -> list[dict[str, Any]]:
    where = "" if include_hidden else "AND c.sellable=1"
    return fetch_all(
        "SELECT c.*,COALESCE((SELECT SUM(i.quantity) FROM register_sale_items i JOIN register_sales s ON s.id=i.sale_id "
        "WHERE i.catalog_item_id=c.id AND i.track_stock=1 AND i.inventory_posted_to_fic=0 "
        "AND s.status IN ('awaiting_payment','paid')),0) local_quantity_committed "
        "FROM register_catalog_items c WHERE c.estate_id=%s " + where +
        " ORDER BY FIELD(c.source_type,'fattureincloud','hospitality','manual'),c.display_order,c.name",
        (estate_id(),),
    )


def _decorate_catalog(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        if row.get("track_stock") and row.get("source_stock_quantity") is not None:
            row["available_quantity"] = Decimal(str(row["source_stock_quantity"])) - Decimal(str(row.get("local_quantity_committed") or 0))
        else:
            row["available_quantity"] = None
    return rows


def _validate_month(month: str | None) -> str:
    candidate = month or date.today().strftime("%Y-%m")
    try:
        datetime.strptime(candidate, "%Y-%m")
    except ValueError as error:
        raise HTTPException(422, "Month must use YYYY-MM") from error
    return candidate


def ledger(month: str | None = None) -> dict[str, Any]:
    selected = _validate_month(month)
    rows = fetch_all(
        "SELECT s.*,COUNT(i.id) line_count,COALESCE(SUM(i.quantity),0) item_quantity FROM register_sales s "
        "LEFT JOIN register_sale_items i ON i.sale_id=s.id WHERE s.estate_id=%s AND DATE_FORMAT(s.created_at,'%%Y-%%m')=%s "
        "GROUP BY s.id ORDER BY s.created_at DESC",
        (estate_id(), selected),
    )
    summary = fetch_one(
        "SELECT COUNT(*) transaction_count,COALESCE(SUM(total_eur),0) gross_eur,COALESCE(SUM(vat_eur),0) vat_eur,"
        "COALESCE(SUM(discount_eur),0) discount_eur,COALESCE(SUM(payment_method='cash'),0) cash_count,"
        "COALESCE(SUM(payment_method='paypal'),0) paypal_count,COALESCE(SUM(payment_method='paypal_pos'),0) paypal_pos_count,"
        "COALESCE(SUM(CASE WHEN currency='EUR' THEN tender_total ELSE 0 END),0) eur_tender_total,"
        "COALESCE(SUM(CASE WHEN currency='USD' THEN tender_total ELSE 0 END),0) usd_tender_total,"
        "COALESCE(SUM(currency='EUR'),0) eur_transaction_count,COALESCE(SUM(currency='USD'),0) usd_transaction_count "
        "FROM register_sales "
        "WHERE estate_id=%s AND status='paid' AND DATE_FORMAT(completed_at,'%%Y-%%m')=%s",
        (estate_id(), selected),
    ) or {}
    return json_ready({"month": selected, "sales": rows, "summary": summary})


def dashboard(month: str | None = None) -> dict[str, Any]:
    sync_hospitality_catalog()
    settings = get_settings()
    checkpoint = fetch_one(
        "SELECT last_success_at,last_attempt_at,last_error,metadata FROM sync_checkpoints WHERE estate_id=%s AND integration_name='fattureincloud_products'",
        (estate_id(),),
    ) or {}
    return json_ready({
        "catalog": _decorate_catalog(_catalog_rows()),
        "inventory": _decorate_catalog(_catalog_rows(True)),
        "ledger": ledger(month),
        "settings": register_settings(),
        "integrations": {
            "fattureincloud": {
                "configured": bool(settings.fattureincloud_token and settings.fattureincloud_company_id),
                "inventory_read_only": True,
                "sales_posting_enabled": False,
                "checkpoint": checkpoint,
            },
            "paypal": {
                "environment": settings.paypal_environment,
                "currencies": ["EUR", "USD"],
                "accounts": {
                    "us": {
                        "configured": bool(settings.paypal_client_id and settings.paypal_client_secret),
                        "client_id": settings.paypal_client_id if settings.paypal_client_id and settings.paypal_client_secret else "",
                        "label": "US PayPal Business",
                    },
                    "it": {
                        "configured": bool(settings.paypal_it_client_id and settings.paypal_it_client_secret),
                        "client_id": settings.paypal_it_client_id if settings.paypal_it_client_id and settings.paypal_it_client_secret else "",
                        "label": "Italian PayPal Business",
                    },
                },
            },
        },
    })


def save_manual_catalog_item(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Item name is required")
    item_id = new_id()
    gross = _money(payload.get("gross_price_eur"))
    vat = _decimal(payload.get("vat_rate", register_settings()["default_vat_rate"]), "VAT rate", Decimal("0"), Decimal("100"))
    stock_value = payload.get("source_stock_quantity")
    stock = None if stock_value in (None, "") else _decimal(stock_value, "Stock quantity", Decimal("0"))
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO register_catalog_items (id,estate_id,source_type,external_id,name,sku,description,category,unit,gross_price_eur,net_price_eur,vat_rate,track_stock,source_stock_quantity,source_stock_updated_at,sellable,price_editable,display_order) "
            "VALUES (%s,%s,'manual',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),1,1,%s)",
            (item_id, estate_id(), item_id, name[:220], str(payload.get("sku") or "")[:100] or None,
             str(payload.get("description") or "") or None, str(payload.get("category") or "Manual")[:120],
             str(payload.get("unit") or "each")[:40], gross, (gross / (Decimal("1") + vat / Decimal("100"))).quantize(CENT) if vat else gross,
             vat, 1 if stock is not None else 0, stock, int(payload.get("display_order") or 100)),
        )
        audit(cursor, "create", "register_catalog_item", item_id, payload, actor)
    return json_ready(fetch_one("SELECT * FROM register_catalog_items WHERE id=%s", (item_id,)) or {})


def update_catalog_item(item_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM register_catalog_items WHERE estate_id=%s AND id=%s", (estate_id(), item_id))
    if not row:
        raise HTTPException(404, "Register item not found")
    gross = _money(payload.get("gross_price_eur", row["gross_price_eur"]))
    vat = _decimal(payload.get("vat_rate", row["vat_rate"]), "VAT rate", Decimal("0"), Decimal("100"))
    stock_value = payload.get("source_stock_quantity", row.get("source_stock_quantity"))
    stock = None if stock_value in (None, "") else _decimal(stock_value, "Stock quantity", Decimal("0"))
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE register_catalog_items SET name=%s,sku=%s,category=%s,unit=%s,gross_price_eur=%s,vat_rate=%s,"
            "track_stock=%s,source_stock_quantity=%s,source_stock_updated_at=NOW(),sellable=%s,display_order=%s WHERE estate_id=%s AND id=%s",
            (str(payload.get("name", row["name"]))[:220], str(payload.get("sku", row.get("sku")) or "")[:100] or None,
             str(payload.get("category", row.get("category")) or "")[:120] or None, str(payload.get("unit", row["unit"]))[:40],
             gross, vat, 1 if stock is not None else 0, stock, 1 if payload.get("sellable", row["sellable"]) else 0,
             int(payload.get("display_order", row["display_order"])), estate_id(), item_id),
        )
        audit(cursor, "update", "register_catalog_item", item_id, payload, actor)
    return json_ready(fetch_one("SELECT * FROM register_catalog_items WHERE id=%s", (item_id,)) or {})


def _receipt_number() -> str:
    return f"REG-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{new_id()[:4].upper()}"


def create_sale(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    lines = payload.get("items")
    if not isinstance(lines, list) or not lines or len(lines) > 100:
        raise HTTPException(422, "Add between 1 and 100 items")
    prepared: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    total = Decimal("0")
    vat_total = Decimal("0")
    for index, line in enumerate(lines, start=1):
        catalog = None
        catalog_id = str(line.get("catalog_item_id") or "").strip()
        if catalog_id:
            catalog = fetch_one("SELECT * FROM register_catalog_items WHERE estate_id=%s AND id=%s AND sellable=1", (estate_id(), catalog_id))
            if not catalog:
                raise HTTPException(422, f"Item {index} is no longer available")
        source_type = catalog["source_type"] if catalog else "manual"
        name = str((catalog or {}).get("name") or line.get("item_name") or "").strip()
        if not name:
            raise HTTPException(422, f"Item {index} needs a name")
        quantity = _decimal(line.get("quantity", 1), f"Item {index} quantity", Decimal("0.001"), Decimal("100000")).quantize(THREE)
        unit_price = _decimal(line.get("unit_gross_eur", (catalog or {}).get("gross_price_eur", 0)), f"Item {index} price").quantize(Decimal("0.0001"))
        discount = _decimal(line.get("discount_percent", 0), f"Item {index} discount", Decimal("0"), Decimal("100"))
        vat_rate = _decimal(line.get("vat_rate", (catalog or {}).get("vat_rate", register_settings()["default_vat_rate"])), f"Item {index} VAT", Decimal("0"), Decimal("100"))
        before = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = (before * (Decimal("100") - discount) / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        line_vat = (gross * vat_rate / (Decimal("100") + vat_rate)).quantize(CENT, rounding=ROUND_HALF_UP) if vat_rate else Decimal("0")
        subtotal += before
        total += gross
        vat_total += line_vat
        prepared.append({
            "line_number": index, "catalog_item_id": catalog_id or None, "source_type": source_type,
            "external_id": (catalog or {}).get("external_id"), "item_name": name[:220], "sku": (catalog or {}).get("sku"),
            "unit": str((catalog or {}).get("unit") or line.get("unit") or "each")[:40], "quantity": quantity,
            "unit_gross_eur": unit_price, "discount_percent": discount, "vat_rate": vat_rate,
            "line_gross_eur": gross, "line_vat_eur": line_vat, "track_stock": 1 if (catalog or {}).get("track_stock") else 0,
        })
    sale_id = new_id()
    receipt = _receipt_number()
    currency = str(payload.get("currency") or "EUR").upper()
    if currency not in {"EUR", "USD"}:
        raise HTTPException(422, "Checkout currency must be EUR or USD")
    paypal_account = str(payload.get("paypal_account") or ("it" if currency == "EUR" else "us")).casefold()
    if paypal_account not in {"us", "it"}:
        raise HTTPException(422, "PayPal account must be US or Italian")
    checkout_language = str(payload.get("checkout_language") or "en").casefold()
    if checkout_language not in {"en", "it"}:
        raise HTTPException(422, "Checkout language must be English or Italian")
    usd_per_eur = _decimal(register_settings().get("usd_per_eur", 1.1567), "USD per EUR", Decimal("0.1"), Decimal("10"))
    tender_total = (total * usd_per_eur if currency == "USD" else total).quantize(CENT, rounding=ROUND_HALF_UP)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO register_sales (id,estate_id,receipt_number,status,payment_status,discount_eur,subtotal_eur,vat_eur,total_eur,currency,paypal_account,checkout_language,tender_total,usd_per_eur,customer_name,customer_email,hospitality_reservation_id,notes,fic_sync_status,created_by) "
            "VALUES (%s,%s,%s,'draft','unpaid',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'not_required',%s)",
            (sale_id, estate_id(), receipt, subtotal-total, subtotal, vat_total, total, currency, paypal_account, checkout_language, tender_total, usd_per_eur,
             str(payload.get("customer_name") or "")[:220] or None, str(payload.get("customer_email") or "")[:190] or None,
             str(payload.get("hospitality_reservation_id") or "") or None, str(payload.get("notes") or "") or None, actor),
        )
        for line in prepared:
            cursor.execute(
                "INSERT INTO register_sale_items (id,sale_id,line_number,catalog_item_id,source_type,external_id,item_name,sku,unit,quantity,unit_gross_eur,discount_percent,vat_rate,line_gross_eur,line_vat_eur,track_stock) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_id(), sale_id, line["line_number"], line["catalog_item_id"], line["source_type"], line["external_id"], line["item_name"], line["sku"], line["unit"], line["quantity"], line["unit_gross_eur"], line["discount_percent"], line["vat_rate"], line["line_gross_eur"], line["line_vat_eur"], line["track_stock"]),
            )
        audit(cursor, "create", "register_sale", sale_id, {"receipt_number": receipt, "total_eur": str(total), "currency": currency, "paypal_account": paypal_account, "checkout_language": checkout_language, "tender_total": str(tender_total), "items": len(prepared)}, actor)
    return sale(sale_id)


def sale(sale_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM register_sales WHERE estate_id=%s AND id=%s", (estate_id(), sale_id))
    if not row:
        raise HTTPException(404, "Register sale not found")
    row["items"] = fetch_all("SELECT * FROM register_sale_items WHERE sale_id=%s ORDER BY line_number", (sale_id,))
    row["receipt_settings"] = register_settings()
    return json_ready(row)


def _lock_and_validate_stock(cursor: Any, sale_id: str) -> None:
    cursor.execute("SELECT id,status FROM register_sales WHERE estate_id=%s AND id=%s FOR UPDATE", (estate_id(), sale_id))
    current = cursor.fetchone()
    if not current:
        raise HTTPException(404, "Register sale not found")
    if current["status"] not in {"draft", "awaiting_payment"}:
        raise HTTPException(409, "This sale can no longer be paid")
    cursor.execute(
        "SELECT i.catalog_item_id,i.item_name,i.quantity,c.source_stock_quantity FROM register_sale_items i "
        "JOIN register_catalog_items c ON c.id=i.catalog_item_id WHERE i.sale_id=%s AND i.track_stock=1 FOR UPDATE",
        (sale_id,),
    )
    for line in cursor.fetchall():
        if line.get("source_stock_quantity") is None:
            continue
        cursor.execute(
            "SELECT COALESCE(SUM(i.quantity),0) committed FROM register_sale_items i JOIN register_sales s ON s.id=i.sale_id "
            "WHERE i.catalog_item_id=%s AND i.sale_id<>%s AND i.inventory_posted_to_fic=0 AND s.status IN ('awaiting_payment','paid')",
            (line["catalog_item_id"], sale_id),
        )
        committed = Decimal(str((cursor.fetchone() or {}).get("committed") or 0))
        available = Decimal(str(line["source_stock_quantity"])) - committed
        if Decimal(str(line["quantity"])) > available:
            raise HTTPException(409, f"Not enough stock for {line['item_name']} ({available} available)")


def complete_cash_sale(sale_id: str, actor: str) -> dict[str, Any]:
    if not register_settings().get("allow_cash", True):
        raise HTTPException(409, "Cash payments are disabled")
    with transaction() as (_, cursor):
        _lock_and_validate_stock(cursor, sale_id)
        cursor.execute(
            "UPDATE register_sales SET status='paid',payment_method='cash',payment_status='paid',completed_at=NOW(),fic_sync_status='not_required' WHERE id=%s",
            (sale_id,),
        )
        audit(cursor, "complete", "register_sale", sale_id, {"payment_method": "cash", "fic_posting": "disabled"}, actor)
    return sale(sale_id)


def complete_paypal_pos_sale(sale_id: str, reference: str, actor: str) -> dict[str, Any]:
    """Record an operator-confirmed PayPal POS Tap to Pay transaction.

    Tap to Pay operates in PayPal's mobile POS application on an NFC phone.
    This path never claims that the browser initiated or verified the charge;
    it requires the operator's transaction reference and preserves it for audit.
    """
    if not register_settings().get("allow_paypal_pos", True):
        raise HTTPException(409, "PayPal Tap to Pay recording is disabled")
    terminal_reference = str(reference or "").strip()
    if len(terminal_reference) < 3:
        raise HTTPException(422, "Enter the approved PayPal POS transaction reference")
    with transaction() as (_, cursor):
        _lock_and_validate_stock(cursor, sale_id)
        cursor.execute(
            "UPDATE register_sales SET status='paid',payment_method='paypal_pos',payment_status='paid',paypal_status='operator_confirmed_pos',terminal_reference=%s,completed_at=NOW(),fic_sync_status='not_required' WHERE id=%s",
            (terminal_reference[:160], sale_id),
        )
        audit(cursor, "complete", "register_sale", sale_id, {"payment_method": "paypal_pos", "verification": "operator_confirmed", "terminal_reference": terminal_reference[:160], "fic_posting": "disabled"}, actor)
    return sale(sale_id)


def void_sale(sale_id: str, actor: str) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute("SELECT status FROM register_sales WHERE estate_id=%s AND id=%s FOR UPDATE", (estate_id(), sale_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Register sale not found")
        if row["status"] == "paid":
            raise HTTPException(409, "A paid sale requires a refund workflow; it cannot be voided")
        cursor.execute("UPDATE register_sales SET status='void',payment_status='failed' WHERE id=%s", (sale_id,))
        audit(cursor, "void", "register_sale", sale_id, {}, actor)
    return sale(sale_id)


def _paypal_base() -> str:
    return "https://api-m.paypal.com" if get_settings().paypal_environment.casefold() == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_request(path: str, method: str = "POST", payload: dict[str, Any] | None = None, token: str | None = None, form: bytes | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = form if form is not None else (json.dumps(payload).encode() if payload is not None else None)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(_paypal_base() + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise HTTPException(502, f"PayPal rejected the request: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, "PayPal is temporarily unavailable") from error


def _paypal_credentials(account: str) -> tuple[str, str]:
    settings = get_settings()
    if account == "it":
        client_id, client_secret, label = settings.paypal_it_client_id, settings.paypal_it_client_secret, "Italian PayPal Business"
    else:
        client_id, client_secret, label = settings.paypal_client_id, settings.paypal_client_secret, "US PayPal Business"
    if not client_id or not client_secret:
        raise HTTPException(409, f"{label} is not configured")
    return client_id, client_secret


def _paypal_token(account: str) -> str:
    client_id, client_secret = _paypal_credentials(account)
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = urllib.request.Request(
        _paypal_base() + "/v1/oauth2/token", data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(), method="POST",
        headers={"Authorization": f"Basic {encoded}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            token = json.loads(response.read().decode()).get("access_token")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:500]
        raise HTTPException(502, f"PayPal authentication failed: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise HTTPException(502, "PayPal is temporarily unavailable") from error
    if not token:
        raise HTTPException(502, "PayPal did not return an access token")
    return str(token)


def create_paypal_order(sale_id: str, actor: str) -> dict[str, Any]:
    row = sale(sale_id)
    with transaction() as (_, cursor):
        _lock_and_validate_stock(cursor, sale_id)
        cursor.execute("UPDATE register_sales SET status='awaiting_payment',payment_method='paypal',payment_status='pending' WHERE id=%s", (sale_id,))
    try:
        result = _paypal_request(
            "/v2/checkout/orders", payload={"intent": "CAPTURE", "purchase_units": [{
                "reference_id": sale_id, "custom_id": sale_id, "invoice_id": row["receipt_number"],
                "amount": {"currency_code": row["currency"], "value": f"{Decimal(str(row['tender_total'])):.2f}"},
                "description": f"Tenuta Baiamonte {row['receipt_number']}",
            }]}, token=_paypal_token(row["paypal_account"]),
        )
    except Exception:
        with transaction() as (_, cursor):
            cursor.execute("UPDATE register_sales SET status='draft',payment_method=NULL,payment_status='failed' WHERE id=%s AND status='awaiting_payment'", (sale_id,))
        raise
    order_id = str(result.get("id") or "")
    if not order_id:
        with transaction() as (_, cursor):
            cursor.execute(
                "UPDATE register_sales SET status='draft',payment_method=NULL,payment_status='failed' "
                "WHERE id=%s AND status='awaiting_payment'",
                (sale_id,),
            )
        raise HTTPException(502, "PayPal did not create an order")
    with transaction() as (_, cursor):
        cursor.execute("UPDATE register_sales SET paypal_order_id=%s,paypal_status=%s WHERE id=%s", (order_id, result.get("status"), sale_id))
        audit(cursor, "paypal_order", "register_sale", sale_id, {"paypal_order_id": order_id, "paypal_account": row["paypal_account"]}, actor)
    return {"id": order_id, "status": result.get("status")}


def capture_paypal_order(sale_id: str, paypal_order_id: str, actor: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM register_sales WHERE estate_id=%s AND id=%s", (estate_id(), sale_id))
    if not row or row.get("paypal_order_id") != paypal_order_id or row.get("status") != "awaiting_payment":
        raise HTTPException(409, "PayPal order does not match this sale")
    result = _paypal_request(f"/v2/checkout/orders/{urllib.parse.quote(paypal_order_id, safe='')}/capture", payload={}, token=_paypal_token(row["paypal_account"]))
    captures = [capture for unit in result.get("purchase_units") or [] for capture in ((unit.get("payments") or {}).get("captures") or [])]
    capture = captures[0] if captures else {}
    amount = capture.get("amount") or {}
    exact = str(amount.get("currency_code")) == row["currency"] and _money(amount.get("value")) == _money(row["tender_total"])
    completed = result.get("status") == "COMPLETED" and capture.get("status") == "COMPLETED"
    if not (exact and completed):
        with transaction() as (_, cursor):
            cursor.execute("UPDATE register_sales SET status='payment_review',payment_status='review',paypal_status=%s WHERE id=%s", (str(result.get("status") or "UNKNOWN")[:80], sale_id))
            audit(cursor, "payment_review", "register_sale", sale_id, {"paypal": result}, actor)
        raise HTTPException(409, "PayPal payment needs review; the captured amount or status did not match")
    with transaction() as (_, cursor):
        _lock_and_validate_stock(cursor, sale_id)
        cursor.execute(
            "UPDATE register_sales SET status='paid',payment_status='paid',paypal_capture_id=%s,paypal_status='COMPLETED',completed_at=NOW(),fic_sync_status='not_required' WHERE id=%s",
            (str(capture.get("id") or "")[:120] or None, sale_id),
        )
        audit(cursor, "complete", "register_sale", sale_id, {"payment_method": "paypal", "paypal_order_id": paypal_order_id, "fic_posting": "disabled"}, actor)
    return sale(sale_id)


def record_print(sale_id: str, actor: str) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute("UPDATE register_sales SET print_count=print_count+1 WHERE estate_id=%s AND id=%s", (estate_id(), sale_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Register sale not found")
        audit(cursor, "print", "register_sale", sale_id, {}, actor)
    return sale(sale_id)
