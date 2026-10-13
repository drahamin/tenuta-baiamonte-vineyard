from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date
from decimal import Decimal
from typing import Any

from .config import get_settings
from .db import fetch_one, transaction
from .inventory import convert_inventory_quantity
from .service import estate_id, new_id


API_ROOT = "https://api-v2.fattureincloud.it"
AGRIPLANET_VAT = "03995580879"
ENODORO_VAT = "02035140819"
ENODORO_ENOLOGY_PRODUCTS = {
    "EPE919": ("nutriferm advance", Decimal("1000"), "NUTRIFERM ADVANCE"),
    "EPC852": ("enartiszym color plus", Decimal("250"), "ENARTIS ZYM COLOR PLUS"),
    "ENA026": ("enartisferm q grace", Decimal("500"), "ENARTIS FERM Q GRACE"),
    "EPE548": ("enartispro tinto", Decimal("1000"), "ENARTIS PRO TINTO"),
    "EPE178": ("claril af", Decimal("1000"), "CLARIL AF"),
    "EPC497": ("nutriferm arom plus", Decimal("1000"), "NUTRIFERM AROM PLUS"),
    "EPC436": ("enartisferm es181", Decimal("500"), "ENARTIS FERM SELECTION ES181"),
    "EPC399": ("enartisferm d20", Decimal("500"), "ENARTIS FERM D-20"),
    "EPC843": ("enartiszym rs p", Decimal("100"), "ENARTIS ZYM RSP"),
    "EPE787": ("enartistan rouge", Decimal("1000"), "ENARTIS TAN ROUGE"),
    "ENA029": ("enartispro blanco", Decimal("1000"), "ENARTIS PRO BLANCO"),
}
# Verified line evidence for Fatture in Cloud received documents that are
# stored as non-detailed expenses and therefore expose an empty items_list.
# The fallback is keyed to the exact supplier invoice number and is used only
# when Fatture in Cloud has no line detail of its own.
ENODORO_INVOICE_EVIDENCE = {
    "2751/00/2026": (("EPE919", "NUTRIFERM ADVANCE KG.1", "1.00", "KG", "16.39"),),
    "2745/00/2026": (
        ("EPC852", "ENARTIS ZYM COLOR PLUS KG.0,250", "0.25", "KG", "37.87"),
        ("ENA026", "ENARTIS FERM Q GRACE KG 0.500", "0.50", "KG", "23.48"),
        ("EPE548", "ENARTIS PRO TINTO KG.1", "1.00", "KG", "77.78"),
    ),
    "2527/00/2026": (
        ("EPE178", "CLARIL AF KG.1", "1.00", "KG", "22.96"),
        ("EPC497", "NUTRIFERM AROM PLUS KG.1", "1.00", "KG", "37.15"),
        ("EPC436", "ENARTIS FERM SELECTION ES181 GR.500", "0.50", "KG", "24.11"),
        ("EPC399", "ENARTIS FERM D-20 GR.500", "0.50", "KG", "22.04"),
        ("EPC843", "ENARTIS ZYM RSP GR.100", "0.10", "KG", "15.30"),
        ("EPE787", "ENARTIS TAN ROUGE KG.1 GRANULARE", "1.00", "KG", "27.77"),
        ("ENA029", "ENARTIS PRO BLANCO KG.1 NEW", "1.00", "KG", "72.23"),
    ),
}
STOCK_BASELINE_DATE = date(2026, 1, 1)
AGRIPLANET_STOCK_PRODUCTS = (
    ("SACRON 45", "SACRON 45 WG", Decimal("1"), "kg", "plant_protection", "candidate"),
    ("OSSICLOR 35", "OSSICLOR 35 WG", Decimal("10"), "kg", "plant_protection", "candidate"),
    ("IMPULSIVE", "IMPULSIVE PREMIUM", Decimal("1"), "L", "fertilizer", "support"),
    ("RESOLVE", "RESOLVE", Decimal("5"), "kg", "fertilizer", "support"),
    ("TERRAPLUS SOLUB", "TERRAPLUS SOLUB NPK 8-7-6", Decimal("15"), "kg", "fertilizer", "support"),
    # The supplier description says "X 5 KG", but the owner's physical container
    # and label confirm a liquid product measured and applied by volume.
    ("GEL DI SILICE", "GEL DI SILICE", Decimal("5"), "L", "fertilizer", "support"),
    ("DURACID GRANULARE", "DURACID GRANULARE", Decimal("1"), "kg", "plant_protection", "support"),
    ("DRAKER 10.2", "DRAKER 10.2", Decimal("1"), "L", "plant_protection", "support"),
    ("NOVATEC CLASSIC", "NOVATEC CLASSIC 12-8-16", Decimal("1"), "kg", "fertilizer", "support"),
)

AGRIPLANET_NON_TREATMENT_MARKERS = (
    "TUBO", "MICROTUBO", "RACCORDO", "MANICOTTO", "VALVOLA", "CURVA", "NIPPLO", "TEE ", "FUSTO", "PIANTA AROMATICA",
)


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
    supplier_name = str((item.get("entity") or {}).get("name") or "").casefold()
    # Nexi card-processing fees are settled through the processor account and
    # are not supplier invoices awaiting a separate Baiamonte payment.
    if "nexi payments" in supplier_name:
        return "paid"
    if payments and all(payment.get("paid_date") or payment.get("status") == "paid" for payment in payments):
        return "paid"
    if any(payment.get("paid_date") or payment.get("status") == "paid" for payment in payments):
        return "part_paid"
    return "unpaid" if payments else "unknown"


def _paid_amount(item: dict[str, Any]) -> Decimal:
    """Return the authoritative amount paid from Fatture in Cloud installments."""
    paid = Decimal("0")
    for payment in item.get("payments_list") or []:
        if not (payment.get("paid_date") or payment.get("status") == "paid"):
            continue
        paid += _money(
            payment.get("amount")
            or payment.get("paid_amount")
            or payment.get("amount_paid")
            or payment.get("value")
        )
    return paid


def _agriplanet_invoice(item: dict[str, Any]) -> bool:
    entity = item.get("entity") or {}
    name = str(entity.get("name") or entity.get("company") or "").casefold()
    vat = "".join(character for character in str(entity.get("vat_number") or entity.get("vat_id") or "") if character.isdigit())
    return "agriplanet" in name.replace(" ", "") or vat == AGRIPLANET_VAT


def _enodoro_invoice(item: dict[str, Any]) -> bool:
    entity = item.get("entity") or {}
    name = str(entity.get("name") or entity.get("company") or "").casefold().replace(" ", "")
    vat = "".join(character for character in str(entity.get("vat_number") or entity.get("vat_id") or "") if character.isdigit())
    return "enodoro" in name or vat == ENODORO_VAT


def _supplier_article_code(line: dict[str, Any]) -> str:
    product = line.get("product") or {}
    for value in (line.get("code"), line.get("product_code"), product.get("code"), product.get("sku")):
        if str(value or "").strip():
            return str(value).strip().upper()[:80]
    text = " ".join(str(value or "") for value in (line.get("name"), line.get("description")))
    for token in text.replace("/", " ").split():
        normalized = token.strip(".,:;-()[]").upper()
        if len(normalized) == 6 and normalized[:3] in {"EPC", "EPE", "ENA"} and normalized[3:].isdigit():
            return normalized
    return ""


def _raw_document_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    return item.get("items_list") or item.get("items") or []


def _document_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return API line items, or exact-invoice evidence for non-detailed expenses."""
    lines = _raw_document_items(item)
    if lines:
        return lines
    invoice_number = str(item.get("invoice_number") or item.get("number") or "").strip()
    return [
        {"code": code, "description": description, "qty": qty, "measure": measure, "net_total": net_total,
         "source": "verified_supplier_invoice_attachment"}
        for code, description, qty, measure, net_total in ENODORO_INVOICE_EVIDENCE.get(invoice_number, ())
    ]


def _hydrate_enodoro_purchase(company: str, resource: str, item: dict[str, Any]) -> dict[str, Any]:
    """Fetch Enodoro detail because FIC list responses can omit product rows."""
    if not _enodoro_invoice(item) or _raw_document_items(item):
        return item
    external_id = str(item.get("id") or "").strip()
    if not external_id:
        return item
    payload = _get(
        f"/c/{company}/{resource}/{urllib.parse.quote(external_id, safe='')}",
        {"fieldset": "detailed"},
    )
    detail = payload.get("data") or {}
    if not isinstance(detail, dict):
        return item
    # Preserve list-response fields when a detail response omits them, while
    # preferring authoritative detailed fields and line items.
    return {**item, **detail}


def _upsert_enology_purchases(cursor: Any, document_id: str, item: dict[str, Any]) -> dict[str, int]:
    recognized_supplier = _enodoro_invoice(item)
    supplier = str((item.get("entity") or {}).get("name") or "ENODORO SRL")
    invoice_number = str(item.get("invoice_number") or item.get("number") or item.get("id") or "unknown")
    invoice_date = str(item.get("date") or date.today().isoformat())[:10]
    matched = review = 0
    for line_number, line in enumerate(_document_items(item), start=1):
        description = str(line.get("description") or line.get("name") or "Fatture in Cloud line")[:700]
        if not description or description.upper().startswith("/D"):
            continue
        article_code = _supplier_article_code(line)
        cursor.execute(
            "SELECT m.product_catalog_id,m.package_quantity,m.package_unit FROM enology_supplier_product_mappings m "
            "WHERE m.estate_id=%s AND m.supplier_key='enodoro' AND m.active=1 AND (m.supplier_article_code=%s OR UPPER(%s) LIKE CONCAT('%%',UPPER(m.description_alias),'%%')) "
            "ORDER BY (m.supplier_article_code=%s) DESC LIMIT 1",
            (estate_id(), article_code, description, article_code),
        )
        mapping = cursor.fetchone() or {}
        if not mapping:
            fallback = ENODORO_ENOLOGY_PRODUCTS.get(article_code)
            if not fallback:
                upper_description = description.upper()
                fallback = next((spec for spec in ENODORO_ENOLOGY_PRODUCTS.values() if spec[2] in upper_description), None)
            if fallback:
                normalized_name, package_quantity, _ = fallback
                cursor.execute("SELECT id FROM enology_product_catalog WHERE manufacturer='ENARTIS' AND normalized_name=%s LIMIT 1", (normalized_name,))
                product = cursor.fetchone() or {}
                if product.get("id"):
                    mapping = {"product_catalog_id": product["id"], "package_quantity": package_quantity, "package_unit": "g"}
        if not recognized_supplier and not mapping:
            continue
        cursor.execute("SELECT id FROM financial_document_lines WHERE document_id=%s AND line_number=%s", (document_id, line_number))
        financial_line = cursor.fetchone()
        if not financial_line:
            continue
        package_count = _money(line.get("qty") or line.get("quantity") or 1)
        measure = str(line.get("measure") or line.get("unit") or "").strip().casefold()
        if mapping.get("product_catalog_id") and measure in {"kg", "kilogram", "kilograms"}:
            purchased_quantity = package_count * Decimal("1000")
        elif mapping.get("product_catalog_id"):
            purchased_quantity = package_count * _money(mapping.get("package_quantity"))
        else:
            purchased_quantity = None
        status = "matched" if mapping.get("product_catalog_id") else "review"
        cursor.execute("SELECT id FROM enology_product_purchase_lines WHERE financial_document_line_id=%s", (financial_line["id"],))
        existing = cursor.fetchone()
        purchase_id = existing["id"] if existing else new_id()
        cursor.execute(
            "INSERT INTO enology_product_purchase_lines (id,estate_id,financial_document_line_id,product_catalog_id,supplier_name,supplier_article_code,invoice_number,invoice_date,description,package_count,purchased_quantity,purchased_unit,taxable_amount_eur,match_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE product_catalog_id=VALUES(product_catalog_id),supplier_name=VALUES(supplier_name),supplier_article_code=VALUES(supplier_article_code),invoice_number=VALUES(invoice_number),invoice_date=VALUES(invoice_date),description=VALUES(description),package_count=VALUES(package_count),purchased_quantity=VALUES(purchased_quantity),purchased_unit=VALUES(purchased_unit),taxable_amount_eur=VALUES(taxable_amount_eur),match_status=VALUES(match_status)",
            (purchase_id, estate_id(), financial_line["id"], mapping.get("product_catalog_id"), supplier, article_code or None, invoice_number, invoice_date, description, package_count, purchased_quantity, mapping.get("package_unit"), _line_net_amount(line, package_count), status),
        )
        matched += status == "matched"
        review += status == "review"
    return {"matched": int(matched), "review": int(review)}


def _stock_product_match(line: dict[str, Any]) -> tuple[str, Decimal, str, str, str] | None:
    product = line.get("product") or {}
    text = " ".join(str(value or "") for value in (line.get("name"), line.get("description"), product.get("name"), product.get("description"))).upper()
    for marker, product_name, package_size, unit, product_type, relevance in AGRIPLANET_STOCK_PRODUCTS:
        if marker in text:
            return product_name, package_size, unit, product_type, relevance
    return None


def _line_net_amount(line: dict[str, Any], package_count: Decimal) -> Decimal:
    total = _money(line.get("net_total") or line.get("total_net") or line.get("amount_net"))
    return total if total else _money(line.get("net_price") or line.get("price_net") or line.get("price")) * package_count


def _historical_stock_receipt(invoice_date: str) -> bool:
    """Classify a receipt before any evidence or inventory branch consumes the flag."""
    return date.fromisoformat(str(invoice_date)[:10]) < STOCK_BASELINE_DATE


def _upsert_agriplanet_stock(cursor: Any, item: dict[str, Any]) -> dict[str, int]:
    """Mirror recognized Agriplanet lines into local stock without writing back to Fatture in Cloud."""
    external_id = str(item.get("id") or "").strip()
    if not external_id or not _agriplanet_invoice(item):
        return {"stocked": 0, "review": 0}
    invoice_number = str(item.get("invoice_number") or item.get("number") or external_id)
    invoice_date = str(item.get("date") or date.today().isoformat())[:10]
    historical = _historical_stock_receipt(invoice_date)
    source_filename = f"fattureincloud-received-{external_id}"
    supplier = str((item.get("entity") or {}).get("name") or "AGRIPLANET S.R.L.")
    used_evidence: set[str] = set()
    imported = 0
    review = 0
    for line_number, line in enumerate(item.get("items_list") or [], start=1):
        match = _stock_product_match(line)
        if not match:
            description = str(line.get("description") or line.get("name") or "").strip()[:500]
            normalized = description.upper()
            if not description or normalized.startswith("/D"):
                continue
            package_count = _money(line.get("qty") or line.get("quantity") or 1)
            unit = str(line.get("measure") or line.get("unit") or "PZ")[:30]
            non_treatment = any(marker in normalized for marker in AGRIPLANET_NON_TREATMENT_MARKERS)
            cursor.execute("SELECT id FROM treatment_purchase_evidence WHERE estate_id=%s AND source_filename=%s AND line_number=%s", (estate_id(), source_filename, line_number))
            existing = cursor.fetchone()
            evidence_id = str(existing["id"]) if existing else new_id()
            cursor.execute(
                "INSERT INTO treatment_purchase_evidence (id,estate_id,invoice_date,invoice_number,supplier,source_filename,line_number,description,package_count,package_size,package_unit,quantity_total,quantity_unit,net_amount_eur,vat_rate_pct,treatment_relevance,notes) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE description=VALUES(description),package_count=VALUES(package_count),package_unit=VALUES(package_unit),quantity_total=VALUES(quantity_total),quantity_unit=VALUES(quantity_unit),net_amount_eur=VALUES(net_amount_eur),vat_rate_pct=VALUES(vat_rate_pct),treatment_relevance=VALUES(treatment_relevance),notes=VALUES(notes)",
                (evidence_id, estate_id(), invoice_date, invoice_number, supplier, source_filename, line_number, description, package_count, unit, package_count, unit, _line_net_amount(line, package_count), _money((line.get("vat") or {}).get("value") if isinstance(line.get("vat"), dict) else line.get("vat")), "not_treatment" if non_treatment else "support", "Historical/current Agriplanet non-treatment supply line imported from Fatture in Cloud; not included in treatment stock." if non_treatment else "Unclassified Agriplanet line. Review product identity, package size and treatment relevance before posting stock or using it in a prediction."),
            )
            if not non_treatment:
                review += 1
            continue
        product_name, package_size, unit, product_type, relevance = match
        package_count = _money(line.get("qty") or line.get("quantity") or 1)
        quantity_total = package_count * package_size
        net_amount = _line_net_amount(line, package_count)
        description = str(line.get("description") or line.get("name") or product_name)[:500]
        cursor.execute("SELECT id,unit FROM products WHERE estate_id=%s AND name=%s", (estate_id(), product_name))
        product = cursor.fetchone()
        if not product:
            product_id = new_id()
            cursor.execute(
                "INSERT INTO products (id,estate_id,name,product_type,unit,supplier,notes,active) VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                (product_id, estate_id(), product_name, product_type, unit, supplier, "Created automatically from an Agriplanet invoice line; label and authorization details still require verification before treatment use."),
            )
            product = {"id": product_id, "unit": unit}
        stock_quantity = convert_inventory_quantity(quantity_total, unit, product.get("unit"))
        unit_review = stock_quantity is None
        evidence_note = f"Historical Agriplanet supply receipt from Fatture in Cloud document {external_id}; retained for year-over-year history and closed before the owner-confirmed zero-stock baseline on 2026-01-01." if historical else f"Automatic 2026 stock receipt from Fatture in Cloud received document {external_id}."
        if unit_review:
            evidence_note += f" [STOCK REVIEW] Invoice quantity is {quantity_total} {unit}, while this product is managed in {product.get('unit') or 'an unknown unit'}; excluded from on-hand stock until density or a physical count is recorded."
        cursor.execute(
            "SELECT id FROM treatment_purchase_evidence WHERE estate_id=%s AND invoice_number=%s AND invoice_date=%s AND product_id=%s ORDER BY line_number",
            (estate_id(), invoice_number, invoice_date, product["id"]),
        )
        existing_matches = [row for row in cursor.fetchall() if str(row["id"]) not in used_evidence]
        existing = existing_matches[0] if existing_matches else None
        if not existing:
            cursor.execute("SELECT id FROM treatment_purchase_evidence WHERE estate_id=%s AND source_filename=%s AND line_number=%s", (estate_id(), source_filename, line_number))
            existing = cursor.fetchone()
        evidence_id = str(existing["id"]) if existing else new_id()
        used_evidence.add(evidence_id)
        cursor.execute(
            "INSERT INTO treatment_purchase_evidence (id,estate_id,product_id,invoice_date,invoice_number,supplier,source_filename,line_number,description,package_count,package_size,package_unit,quantity_total,quantity_unit,net_amount_eur,vat_rate_pct,treatment_relevance,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),description=VALUES(description),package_count=VALUES(package_count),package_size=VALUES(package_size),package_unit=VALUES(package_unit),quantity_total=VALUES(quantity_total),quantity_unit=VALUES(quantity_unit),net_amount_eur=VALUES(net_amount_eur),vat_rate_pct=VALUES(vat_rate_pct),treatment_relevance=VALUES(treatment_relevance),notes=VALUES(notes)",
            (evidence_id, estate_id(), product["id"], invoice_date, invoice_number, supplier, source_filename, line_number, description, package_count, package_size, unit, quantity_total, unit, net_amount, _money((line.get("vat") or {}).get("value") if isinstance(line.get("vat"), dict) else line.get("vat")), relevance, evidence_note),
        )
        cursor.execute("SELECT id,reference_type FROM inventory_movements WHERE estate_id=%s AND reference_id=%s AND reference_type='fattureincloud_stock' ORDER BY movement_date LIMIT 1", (estate_id(), evidence_id))
        movement = cursor.fetchone()
        movement_id = movement["id"] if movement else new_id()
        posted_quantity = stock_quantity if stock_quantity is not None else Decimal("0")
        unit_cost = net_amount / posted_quantity if posted_quantity else Decimal("0")
        movement_note = f"Stock received from {supplier}, invoice {invoice_number}; Fatture in Cloud document {external_id}."
        if unit_review:
            movement_note += f" Excluded from on-hand: invoice {quantity_total} {unit} cannot be converted safely to {product.get('unit') or 'the stock unit'} without density or a physical count."
        cursor.execute(
            "INSERT INTO inventory_movements (id,estate_id,product_id,movement_date,movement_type,quantity_delta,unit_cost_eur,reference_type,reference_id,notes) "
            "VALUES (%s,%s,%s,%s,'purchase',%s,%s,'fattureincloud_stock',%s,%s) "
            "ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),movement_date=VALUES(movement_date),quantity_delta=VALUES(quantity_delta),unit_cost_eur=VALUES(unit_cost_eur),reference_type=VALUES(reference_type),reference_id=VALUES(reference_id),notes=VALUES(notes)",
            (movement_id, estate_id(), product["id"], invoice_date, posted_quantity, unit_cost, evidence_id, movement_note),
        )
        if historical:
            cursor.execute("SELECT id FROM inventory_movements WHERE estate_id=%s AND reference_id=%s AND reference_type='historical_stock_closed_2026_baseline' LIMIT 1", (estate_id(), evidence_id))
            closing = cursor.fetchone()
            closing_id = closing["id"] if closing else new_id()
            cursor.execute(
                "INSERT INTO inventory_movements (id,estate_id,product_id,movement_date,movement_type,quantity_delta,unit_cost_eur,reference_type,reference_id,notes) "
                "VALUES (%s,%s,%s,'2025-12-31 23:59:59','adjustment',%s,%s,'historical_stock_closed_2026_baseline',%s,%s) "
                "ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),movement_date=VALUES(movement_date),quantity_delta=VALUES(quantity_delta),unit_cost_eur=VALUES(unit_cost_eur),notes=VALUES(notes)",
                (closing_id, estate_id(), product["id"], -posted_quantity, unit_cost, evidence_id, "Closes historical Agriplanet quantity so the owner-confirmed 2026-01-01 opening stock remains zero."),
            )
        if unit_review:
            review += 1
        else:
            imported += 1
    return {"stocked": imported, "review": review}


PACKAGING_LINE_MARKERS = (
    ("back_label", "Back wine label", ("ETICHETTE RETRO", "RETROETICHET", "BACK LABEL")),
    ("front_label", "Front wine label", ("ETICHETTE FRONTE", "FRONT LABEL", "ETICHETTA FRONTE")),
    ("bottle", "Bottling glass bottle 750 ml", ("BORG. VIRGO", "BORG VIRGO", "BOTTIGLIA 750", "BOTTIGLIE 750")),
    ("cork", "Natural cork 44x24 mm", ("TAPPI SUGH", "TAPPO SUGH", "SUGHERO 44X24")),
    ("capsule", "Polylaminate bottle capsule", ("CHIUSURE POLYTECH", "CAPSUL", "POLYLAMINAT")),
    ("case", "Six-bottle case box", ("IMB.305", "SCATOLA 6", "CARTONE 6", "CASE BOX")),
)

PACKAGING_SUPPLIERS = {
    "bottle": ("MEDITERRANEA VETRI",),
    "cork": ("PARRAMON",),
    "front_label": ("WELABEL", "UMBRA LABEL"),
    "back_label": ("WELABEL", "UMBRA LABEL"),
    "capsule": ("INTERCAP",),
    "case": ("SCIA",),
}


def _packaging_product(cursor: Any, line: dict[str, Any], supplier: str = "") -> str | None:
    product = line.get("product") or {}
    text = " ".join(str(value or "") for value in (line.get("name"), line.get("description"), product.get("name"), product.get("description"))).upper()
    supplier_text = supplier.upper()
    for category, product_name, markers in PACKAGING_LINE_MARKERS:
        if any(marker in text for marker in markers):
            allowed = PACKAGING_SUPPLIERS.get(category, ())
            if supplier_text and allowed and not any(marker in supplier_text for marker in allowed):
                return None
            cursor.execute("SELECT id FROM products WHERE estate_id=%s AND name=%s", (estate_id(), product_name))
            row = cursor.fetchone()
            return str(row["id"]) if row else None
    return None


def _upsert_document_lines(cursor: Any, document_id: str, item: dict[str, Any]) -> int:
    lines = _document_items(item)
    supplier = str((item.get("entity") or {}).get("name") or (item.get("entity") or {}).get("company") or "")
    supplier_key = supplier.upper().replace(" ", "")
    center_code = "VINEYARD" if _agriplanet_invoice(item) else ("CELLAR" if _enodoro_invoice(item) or any(marker in supplier_key for marker in ("GAMBINOSONIA", "SEBASTIANOVINCI", "MEDITERRANEAVETRI", "PARRAMON", "INTERCAP", "SCIA")) else None)
    cursor.execute("SELECT id FROM cost_centers WHERE estate_id=%s AND code=%s", (estate_id(), center_code)) if center_code else None
    center = cursor.fetchone() if center_code else None
    document_year = int(str(item.get("date") or date.today().isoformat())[:4])
    cursor.execute("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), document_year))
    season = cursor.fetchone()
    for line_number, line in enumerate(lines, start=1):
        quantity = _money(line.get("qty") or line.get("quantity") or 1)
        taxable = _line_net_amount(line, quantity)
        unit_price = taxable / quantity if quantity else Decimal("0")
        vat_rate = _money((line.get("vat") or {}).get("value") if isinstance(line.get("vat"), dict) else line.get("vat"))
        description = str(line.get("description") or line.get("name") or "Fatture in Cloud line")[:700]
        product_id = _packaging_product(cursor, line, supplier)
        cursor.execute("SELECT id FROM financial_document_lines WHERE document_id=%s AND line_number=%s", (document_id, line_number))
        existing = cursor.fetchone()
        line_id = existing["id"] if existing else new_id()
        cursor.execute(
            "INSERT INTO financial_document_lines (id,document_id,line_number,description,product_id,cost_center_id,season_id,quantity,unit,unit_price,taxable_amount,vat_rate,vat_amount,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Read-only line mirror from Fatture in Cloud') "
            "ON DUPLICATE KEY UPDATE description=VALUES(description),product_id=VALUES(product_id),cost_center_id=COALESCE(VALUES(cost_center_id),cost_center_id),season_id=COALESCE(VALUES(season_id),season_id),quantity=VALUES(quantity),unit=VALUES(unit),unit_price=VALUES(unit_price),taxable_amount=VALUES(taxable_amount),vat_rate=VALUES(vat_rate),vat_amount=VALUES(vat_amount),notes=VALUES(notes)",
            (line_id, document_id, line_number, description, product_id, (center or {}).get("id"), (season or {}).get("id"), quantity, str(line.get("measure") or line.get("unit") or "each")[:40], unit_price, taxable, vat_rate, taxable * vat_rate / Decimal("100")),
        )
    return len(lines)


def _upsert_document(cursor: Any, item: dict[str, Any], document_type: str, party_type: str) -> str | None:
    external_id = str(item.get("id") or "")
    if not external_id:
        return None
    party_id = _party(cursor, item, party_type)
    net = _money(item.get("amount_net") or item.get("net_price"))
    vat = _money(item.get("amount_vat"))
    gross = _money(item.get("amount_gross") or item.get("gross_price"))
    if not gross:
        gross = net + vat
    number = str(item.get("invoice_number") or item.get("number") or external_id)
    document_date = item.get("date") or date.today().isoformat()
    due_dates = [payment.get("due_date") for payment in item.get("payments_list") or [] if payment.get("due_date")]
    due_date = min(due_dates) if due_dates else None
    status = "paid" if _payment_status(item) == "paid" else ("issued" if document_type == "sales_invoice" else "received")
    cursor.execute("SELECT id FROM financial_documents WHERE estate_id=%s AND source='fattureincloud' AND external_source_id=%s", (estate_id(), external_id))
    existing = cursor.fetchone()
    record_id = existing["id"] if existing else new_id()
    cursor.execute(
        "INSERT INTO financial_documents (id,estate_id,document_type,document_number,document_date,due_date,party_id,currency,taxable_amount,vat_amount,gross_total,status,payment_status,source_paid_amount,source,source_document,external_source_id,notes) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'fattureincloud',%s,%s,'Read-only mirror from Fatture in Cloud') "
        "ON DUPLICATE KEY UPDATE due_date=VALUES(due_date),party_id=VALUES(party_id),currency=VALUES(currency),taxable_amount=VALUES(taxable_amount),vat_amount=VALUES(vat_amount),gross_total=VALUES(gross_total),status=VALUES(status),payment_status=VALUES(payment_status),source_paid_amount=VALUES(source_paid_amount),source='fattureincloud',source_document=VALUES(source_document),external_source_id=VALUES(external_source_id),updated_at=NOW()",
        (record_id, estate_id(), document_type, number, document_date, due_date, party_id, item.get("currency", {}).get("id") or "EUR", net, vat, gross, status, _payment_status(item), _paid_amount(item), item.get("url") or item.get("attachment_url"), external_id),
    )
    return str(record_id)


def pull_register_products() -> dict[str, Any]:
    """Mirror the Fatture in Cloud product catalog for the local register.

    This remains read-only toward Fatture in Cloud. Local sales are retained in
    the register ledger and deducted from the mirrored quantity until a future
    receipt integration explicitly reconciles them.
    """
    settings = get_settings()
    if not settings.fattureincloud_token or not settings.fattureincloud_company_id:
        return {"configured": False, "products": 0, "message": "Fatture in Cloud is not configured"}
    company = urllib.parse.quote(settings.fattureincloud_company_id, safe="")
    products: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _get(f"/c/{company}/products", {"page": page, "per_page": 100, "fieldset": "detailed", "sort": "name"})
        products.extend(payload.get("data") or [])
        pagination = (payload.get("meta") or {}).get("pagination") or payload
        last_page = int(pagination.get("last_page") or pagination.get("page_count") or page)
        if page >= last_page:
            break
        page += 1
    with transaction() as (_, cursor):
        for item in products:
            external_id = str(item.get("id") or "").strip()
            if not external_id:
                continue
            vat = item.get("default_vat") if isinstance(item.get("default_vat"), dict) else {}
            vat_rate = _money(vat.get("value"))
            net = _money(item.get("net_price"))
            gross = _money(item.get("gross_price"))
            if not gross and net:
                gross = net * (Decimal("1") + vat_rate / Decimal("100"))
            tracked = bool(item.get("in_stock"))
            stock = _money(item.get("stock_current")) if tracked else None
            cursor.execute(
                "SELECT id FROM register_catalog_items WHERE estate_id=%s AND source_type='fattureincloud' AND external_id=%s",
                (estate_id(), external_id),
            )
            existing = cursor.fetchone()
            item_id = existing["id"] if existing else new_id()
            cursor.execute(
                "INSERT INTO register_catalog_items "
                "(id,estate_id,source_type,external_id,name,sku,description,category,unit,gross_price_eur,net_price_eur,vat_rate,fic_vat_id,track_stock,source_stock_quantity,source_stock_updated_at,sellable,price_editable,source_payload) "
                "VALUES (%s,%s,'fattureincloud',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,1,%s) "
                "ON DUPLICATE KEY UPDATE name=VALUES(name),sku=VALUES(sku),description=VALUES(description),category=VALUES(category),unit=VALUES(unit),"
                "gross_price_eur=VALUES(gross_price_eur),net_price_eur=VALUES(net_price_eur),vat_rate=VALUES(vat_rate),fic_vat_id=VALUES(fic_vat_id),"
                "track_stock=VALUES(track_stock),source_stock_quantity=VALUES(source_stock_quantity),source_stock_updated_at=NOW(),source_payload=VALUES(source_payload)",
                (
                    item_id, estate_id(), external_id, str(item.get("name") or "Fatture in Cloud product")[:220],
                    str(item.get("code") or "")[:100] or None, str(item.get("description") or "") or None,
                    str(item.get("category") or "")[:120] or None, str(item.get("measure") or "each")[:40],
                    gross, net, vat_rate, vat.get("id"), 1 if tracked else 0, stock,
                    1 if gross > 0 else 0, json.dumps(item, ensure_ascii=False, default=str),
                ),
            )
        cursor.execute(
            "INSERT INTO sync_checkpoints (estate_id,integration_name,last_success_at,last_attempt_at,metadata) "
            "VALUES (%s,'fattureincloud_products',NOW(),NOW(),%s) ON DUPLICATE KEY UPDATE last_success_at=NOW(),last_attempt_at=NOW(),last_error=NULL,metadata=VALUES(metadata)",
            (estate_id(), json.dumps({"products": len(products)})),
        )
    return {"configured": True, "read_only": True, "products": len(products)}


def pull_fattureincloud() -> dict[str, Any]:
    settings = get_settings()
    if not settings.fattureincloud_token or not settings.fattureincloud_company_id:
        return {"configured": False, "message": "Add the Fatture in Cloud manual token and company ID in app configuration."}
    counts = {"sales_invoices": 0, "purchase_invoices": 0, "credit_notes": 0, "delivery_notes": 0, "document_lines": 0, "treatment_stock_lines": 0, "treatment_stock_review_lines": 0, "enology_product_lines": 0, "enology_product_review_lines": 0}
    company = urllib.parse.quote(settings.fattureincloud_company_id, safe="")
    start_year = date.today().year - max(5, settings.fattureincloud_sync_years) + 1
    streams = (("issued_documents", "invoice", "sales_invoice", "customer", "sales_invoices"), ("issued_documents", "credit_note", "credit_note", "customer", "credit_notes"), ("issued_documents", "delivery_note", "delivery_note", "customer", "delivery_notes"), ("received_documents", "expense", "purchase_invoice", "supplier", "purchase_invoices"))
    with transaction() as (_, cursor):
        for resource, source_type, document_type, party_type, counter in streams:
            for year in range(start_year, date.today().year + 1):
                page = 1
                while True:
                    payload = _get(f"/c/{company}/{resource}", {"type": source_type, "q": f"date >= '{year}-01-01' and date <= '{year}-12-31'", "page": page, "per_page": 100, "fieldset": "detailed"})
                    rows = [item for item in (payload.get("data") or []) if str(item.get("date") or "")[:4] == str(year)]
                    for item in rows:
                        if document_type == "purchase_invoice":
                            item = _hydrate_enodoro_purchase(company, resource, item)
                        document_id = _upsert_document(cursor, item, document_type, party_type)
                        if document_id:
                            counts["document_lines"] += _upsert_document_lines(cursor, document_id, item)
                        if document_type == "purchase_invoice":
                            stock_result = _upsert_agriplanet_stock(cursor, item)
                            counts["treatment_stock_lines"] += stock_result["stocked"]
                            counts["treatment_stock_review_lines"] += stock_result["review"]
                            enology_result = _upsert_enology_purchases(cursor, document_id, item)
                            counts["enology_product_lines"] += enology_result["matched"]
                            counts["enology_product_review_lines"] += enology_result["review"]
                        counts[counter] += 1
                    pagination = (payload.get("meta") or {}).get("pagination") or payload
                    last_page = int(pagination.get("last_page") or pagination.get("page_count") or page)
                    if page >= last_page:
                        break
                    page += 1
        cursor.execute("INSERT INTO sync_checkpoints (estate_id,integration_name,last_success_at,last_attempt_at,metadata) VALUES (%s,'fattureincloud',NOW(),NOW(),%s) ON DUPLICATE KEY UPDATE last_success_at=NOW(),last_attempt_at=NOW(),last_error=NULL,metadata=VALUES(metadata)", (estate_id(), json.dumps(counts)))
    try:
        counts["register_products"] = pull_register_products().get("products", 0)
    except Exception as error:
        counts["register_products_error"] = str(error)[:240]
    return {"configured": True, "read_only": True, "counts": counts}
