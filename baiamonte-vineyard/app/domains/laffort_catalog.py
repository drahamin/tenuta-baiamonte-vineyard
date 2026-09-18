"""Official LAFFORT product catalog and guarded enology suggestions."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from html import unescape
import json
import re
import unicodedata
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..db import fetch_all, transaction
from ..enology_measurements import normalize_enology_measurement
from ..service import estate_id, json_ready, new_id


LAFFORT_BASE_URL = "https://laffort.com"
LAFFORT_RANGES = (
    ("zymaflore", "Yeast", "yeast", "/en/ranges/zymaflore-yeast/"),
    ("actiflore", "Yeast", "yeast", "/en/ranges/actiflore-yeast/"),
    ("yeast_derivatives", "Yeast derivatives", "yeast_derivative", "/en/ranges/yeast-derivatives/"),
    ("enzymes", "Enzymes", "enzyme", "/en/ranges/enzyme/"),
    ("bacteria", "Bacteria", "bacteria", "/en/ranges/bacteria/"),
    ("nutrients", "Nutrients", "nutrient", "/en/ranges/nutrients/"),
    ("tannins", "Tannins", "tannin", "/en/ranges/tannins/"),
    ("fining", "Fining", "fining", "/en/ranges/fining/"),
    ("stabilisation", "Stabilisation", "stabilizer", "/en/ranges/stabilisation/"),
    ("specific_treatment", "Specific treatments", "treatment", "/en/ranges/specific-treatment/"),
    ("nobile", "Oak alternatives", "oak", "/en/ranges/nobile/"),
    ("rose", "Rose winemaking", "other", "/en/ranges/rose/"),
    ("sparkling", "Sparkling winemaking", "other", "/en/ranges/sparkling/"),
    ("cleaning", "Cellar cleaning", "cleaning", "/en/ranges/cleaning/"),
    ("filtration", "Filtration", "filtration", "/en/ranges/filtration/"),
    ("preservation", "Wine preservation", "preservation", "/en/ranges/preservation/"),
    ("laboratory", "Laboratory", "laboratory", "/en/ranges/laboratory/"),
    ("equipment", "Cellar equipment", "equipment", "/en/ranges/equipement/"),
)


def normalize_product_name(value: str) -> str:
    value = value.replace("™", " ").replace("®", " ").replace("©", " ")
    value = "".join(character for character in unicodedata.normalize("NFKD", value) if not unicodedata.combining(character))
    normalized = " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", value).casefold().split())
    # The current site expands ALPHA's species shorthand in the heading while
    # older product sheets and the estate protocol use the stable trade name.
    if normalized.startswith("zymaflore alpha "):
        return "zymaflore alpha"
    return normalized


def _plain(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).replace("\xa0", " ").split())


def parse_laffort_range(html: str, *, range_code: str, range_name: str, product_class: str, source_url: str) -> list[dict[str, Any]]:
    """Extract every product card from one official range page."""
    matches = list(re.finditer(r"<h2\b[^>]*>(.*?)</h2>", html, re.I | re.S))
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        heading = match.group(1)
        link = re.search(r'href=["\']([^"\']+/products/[^"\']+)["\']', heading, re.I)
        if not link:
            continue
        name = _plain(heading)
        if not name:
            continue
        block = html[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(html)]
        paragraph = re.search(r"<p\b[^>]*>(.*?)</p>", block, re.I | re.S)
        pdf_links = [urljoin(source_url, unescape(url)) for url in re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', block, re.I)]
        pds = next((url for url in pdf_links if "/FP/" in url or "product" in url.casefold()), None)
        sds = next((url for url in pdf_links if "sds" in url.casefold() or "fds" in url.casefold()), None)
        rows.append({
            "manufacturer": "LAFFORT",
            "product_name": name,
            "normalized_name": normalize_product_name(name),
            "range_code": range_code,
            "range_name": range_name,
            "product_class": product_class,
            "description": _plain(paragraph.group(1)) if paragraph else None,
            "product_url": urljoin(source_url, link.group(1)),
            "pds_url": pds,
            "sds_url": sds,
            "source_url": source_url,
        })
    return rows


def _read_url(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Tenuta-Baiamonte-Enology/1.0 (+official-catalog-sync)"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def sync_laffort_catalog(*, reader: Callable[[str], bytes] = _read_url) -> dict[str, Any]:
    """Refresh all official LAFFORT range pages without inventing dose rules."""
    run_id, checked_at = new_id(), datetime.now()
    rows: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_product_catalog_sync_runs (id,status,source_url) VALUES (%s,'running',%s)", (run_id, f"{LAFFORT_BASE_URL}/en/ranges/"))
    for range_code, range_name, product_class, path in LAFFORT_RANGES:
        source_url = urljoin(LAFFORT_BASE_URL, path)
        try:
            html = reader(source_url).decode("utf-8", errors="replace")
            rows.extend(parse_laffort_range(html, range_code=range_code, range_name=range_name, product_class=product_class, source_url=source_url))
        except Exception as error:
            failures[range_code] = str(error)[:240]
    deduplicated: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["normalized_name"]:
            # Canonical technical ranges are listed before cross-cutting rosé
            # and sparkling collections, so keep the most specific identity.
            deduplicated.setdefault(row["normalized_name"], row)
    with transaction() as (_, cursor):
        if not failures:
            cursor.execute("UPDATE enology_product_catalog SET present_in_latest=0 WHERE manufacturer='LAFFORT'")
        for row in deduplicated.values():
            cursor.execute(
                "INSERT INTO enology_product_catalog (id,manufacturer,product_name,normalized_name,range_code,range_name,product_class,description,product_url,pds_url,sds_url,source_url,source_checked_at,present_in_latest) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),range_code=VALUES(range_code),range_name=VALUES(range_name),product_class=VALUES(product_class),description=VALUES(description),product_url=VALUES(product_url),pds_url=COALESCE(VALUES(pds_url),pds_url),sds_url=COALESCE(VALUES(sds_url),sds_url),source_url=VALUES(source_url),source_checked_at=VALUES(source_checked_at),present_in_latest=1",
                (new_id(), row["manufacturer"], row["product_name"], row["normalized_name"], row["range_code"], row["range_name"], row["product_class"], row["description"], row["product_url"], row["pds_url"], row["sds_url"], row["source_url"], checked_at),
            )
        status = "processed" if not failures else "partial" if deduplicated else "failed"
        cursor.execute("UPDATE enology_product_catalog_sync_runs SET status=%s,source_rows=%s,imported_rows=%s,failed_ranges=%s,error_text=%s,completed_at=NOW(6) WHERE id=%s", (status, len(rows), len(deduplicated), len(failures), json.dumps(failures) if failures else None, run_id))
    return json_ready({"status": status, "products": len(deduplicated), "ranges": len(LAFFORT_RANGES), "failed_ranges": failures})


def catalog_rows() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,manufacturer,product_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,sds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest "
        "FROM enology_product_catalog WHERE active=1 AND present_in_latest=1 ORDER BY manufacturer,range_name,product_name"
    )
    stock = fetch_all(
        "SELECT s.id,s.product_catalog_id,s.stock_key,s.supplier_name,s.product_lot,s.expires_on,s.package_size,s.package_unit,"
        "s.minimum_package_count,s.quantity_status,s.evidence_reference,s.notes "
        "FROM enology_product_stock s WHERE s.estate_id=%s AND s.active=1 ORDER BY s.expires_on,s.stock_key",
        (estate_id(),),
    )
    stock_by_product: dict[str, list[dict[str, Any]]] = {}
    for item in stock:
        stock_by_product.setdefault(str(item["product_catalog_id"]), []).append(item)
    for row in rows:
        row["stock"] = stock_by_product.get(str(row["id"]), [])
        row["in_cellar"] = bool(row["stock"])
    return rows


ADDITIVE_PREDICTION_MODEL = "enology-additive-decisions-v4-alcohol-consistency"


def working_dose_recommendation(
    lot: dict[str, Any], protocol: dict[str, Any], projection: dict[str, Any],
    readings: list[dict[str, Any]], blockers: list[str], timing_status: str,
    additions: list[dict[str, Any]] | None = None,
    lab_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose a transparent working point inside a verified purpose-specific range.

    This never invents a dose outside the product protocol. Bench-trial products and
    products missing a batch basis remain ranges until the required trial/input exists.
    """
    trigger = str(protocol.get("trigger_code") or "")
    if trigger == "alcohol_consistency":
        volume_l = float(lot.get("volume_l") or lot.get("initial_l") or 0)
        current = lot.get("potential_alcohol_pct")
        target = lot.get("target_potential_alcohol_pct")
        conversion = float(protocol.get("dose_min") or 1.68)
        if not volume_l or current is None or target is None:
            return {
                "status": "input_needed", "rate": None, "quantity": None, "unit": "kg",
                "rationale": "Record verified lot volume, current potential alcohol and the estate target alcohol. Compliance is shown separately and does not suppress the technical calculation.",
            }
        lab_metric = ((lab_evidence or {}).get("metrics") or {}).get("potential_alcohol") or {}
        measured_at = _parse_time(lab_metric.get("sampled_at") or lab_metric.get("lab_date"))
        applied_after_measurement = []
        for item in additions or []:
            item_name = normalize_product_name(str(item.get("additive_name") or ""))
            protocol_name = normalize_product_name(str(protocol.get("product_name") or ""))
            same_product = item_name == protocol_name or ("crystalmustgrape" in item_name and "crystalmustgrape" in protocol_name)
            if item.get("event_status") != "applied" or not same_product:
                continue
            applied_at = _parse_time(item.get("applied_at"))
            if measured_at is None or applied_at is None or applied_at >= measured_at:
                applied_after_measurement.append(item)
        already_applied_kg = sum(
            float(item.get("quantity") or 0)
            for item in applied_after_measurement if str(item.get("unit") or "").strip().casefold() == "kg"
        )
        hectolitres = volume_l / 100
        measured = float(current)
        uplift = already_applied_kg / (conversion * hectolitres) if conversion > 0 and hectolitres > 0 else 0
        effective = measured + uplift
        gap = max(0.0, float(target) - effective)
        quantity = gap * conversion * hectolitres
        pending_retest = already_applied_kg > 0
        rationale = (
            f"Manufacturer conversion: {conversion:g} kg/hL raises potential alcohol by 1% vol. "
            f"Measured {measured:g}% vol"
            + (f" plus {already_applied_kg:g} kg recorded after that sample (calculated +{uplift:.2f}% vol)" if already_applied_kg else "")
            + f" gives a working projection of {effective:.2f}% vol against the {float(target):g}% vol estate target."
        )
        if gap <= 0.005:
            rationale += " No further addition is technically indicated."
        else:
            rationale += f" The remaining technical addition is {quantity:.2f} kg for {volume_l:g} L."
        if pending_retest:
            rationale += " Run a post-addition potential-alcohol test to replace the calculated uplift before any further addition."
        return {
            "status": "not_indicated" if gap <= 0.005 else ("recommended_now" if timing_status == "due" else "forecast"),
            "rate": round(gap * conversion, 3), "rate_unit": "kg/hL",
            "quantity": round(quantity, 2), "unit": "kg", "rationale": rationale,
            "measured_potential_alcohol_pct": round(measured, 3),
            "calculated_current_potential_alcohol_pct": round(effective, 3),
            "target_potential_alcohol_pct": round(float(target), 3),
            "projected_potential_alcohol_pct": round(effective + gap, 3),
            "already_applied_kg_since_measurement": round(already_applied_kg, 3),
            "post_addition_test_recommended": pending_retest,
            "compliance_warning": "Technical quantity only. Check current vintage, denomination and enrichment limits before use; the compliance warning does not alter this calculation.",
        }
    if projection.get("status") != "calculated":
        return {"status": "input_needed", "rate": None, "quantity": None, "unit": None, "rationale": "Record the batch volume or fruit weight and a supported product-sheet rate."}
    if trigger in {"bench_trial", "acidification_bench_trial", "pre_bottling_bench"}:
        return {"status": "bench_trial", "rate": None, "quantity": None, "unit": projection.get("unit"), "rationale": "Use the displayed official range for a progressive bench trial; record the selected trial rate before the cellar addition."}
    if blockers:
        return {"status": "input_needed", "rate": None, "quantity": None, "unit": projection.get("unit"), "rationale": "Complete the essential inputs listed below; the official quantity range remains visible meanwhile."}

    low = float(protocol.get("dose_min") if protocol.get("dose_min") is not None else protocol.get("dose_max"))
    high = float(protocol.get("dose_max") if protocol.get("dose_max") is not None else protocol.get("dose_min"))
    rate = low
    rationale = "Use the low end of the verified purpose-specific range for the recorded normal-condition lot."
    fruit_condition = str(lot.get("fruit_condition") or "unknown").casefold()
    potential_alcohol = float(lot.get("potential_alcohol_pct") or 0)
    latest_temp = next((float(row["temp_c"]) for row in reversed(readings) if row.get("temp_c") is not None), None)
    turbidity = lot.get("must_turbidity_ntu")
    yan = lot.get("yan_mg_l")
    yan_target = float(lot.get("yan_target_mg_l") or 150)

    if low == high:
        rationale = "The verified purpose-specific protocol has one rate."
    elif trigger == "inoculation" and (fruit_condition in {"botrytis", "infected"} or potential_alcohol >= 14.5):
        rate = high
        rationale = "Use the high end because recorded fruit condition or potential alcohol indicates a difficult inoculation."
    elif trigger in {"pressing", "must_clarification"} and ((turbidity is not None and float(turbidity) >= 150) or (latest_temp is not None and latest_temp <= 12)):
        rate = high
        rationale = "Use the high end because the must is highly turbid or the recorded process temperature is low."
    elif trigger in {"crusher_or_fermentation", "pump_over", "first_pump_over"} and fruit_condition in {"botrytis", "infected"}:
        rate = high
        rationale = "Use the high end because the fruit condition is recorded as affected."
    elif str(protocol.get("product_name") or "").casefold() == "nutriferm special" and yan is not None:
        deficit = max(0.0, yan_target - float(yan))
        rate = min(high, max(low, deficit / 1.6))
        rationale = f"Working rate uses the sheet's approximate contribution of 16 mg/L YAN per 10 g/hL against the recorded {deficit:g} mg/L deficit, constrained to the verified {low:g}–{high:g} g/hL range; total nutrient accounting still applies."
    elif trigger == "density_drop_30" and yan is not None:
        deficit = max(0.0, yan_target - float(yan))
        fraction = min(1.0, deficit / 100.0)
        rate = low + (high - low) * fraction
        rationale = f"Working rate is interpolated within the verified range from the recorded YAN/APA deficit of {deficit:g} mg/L; total nutrient accounting still applies."

    exact_protocol = {**protocol, "dose_min": rate, "dose_max": rate, "dose_verified": True}
    exact = project_product_quantity(lot.get("volume_l") or lot.get("initial_l"), exact_protocol, fruit_kg=lot.get("fruit_kg"))
    status = "recommended_now" if timing_status == "due" else "forecast"
    return {
        "status": status,
        "rate": round(rate, 2), "rate_unit": protocol.get("dose_unit"),
        "quantity": exact.get("minimum"), "unit": exact.get("unit"),
        "rationale": rationale,
    }


def protocol_rows() -> list[dict[str, Any]]:
    """Return source-verified use cases rather than collapsing a product to one dose."""
    return fetch_all(
        "SELECT r.id,r.product_catalog_id,r.protocol_code,r.protocol_name,r.purpose,r.wine_colors,r.process_stages,r.trigger_code,"
        "r.dose_min,r.dose_max,r.dose_unit,r.dose_basis,r.preparation,r.application_instructions,r.prerequisites,r.required_lab_analytes,r.lab_max_age_days,r.incompatibilities,"
        "r.minimum_contact_hours,r.source_url,r.source_revision,r.verified_on,p.manufacturer,p.product_name,p.product_class,p.pds_url,p.sds_url,p.product_url "
        "FROM enology_product_protocols r JOIN enology_product_catalog p ON p.id=r.product_catalog_id "
        "WHERE r.active=1 AND p.active=1 AND p.present_in_latest=1 ORDER BY p.product_name,r.protocol_name"
    )


def project_product_quantity(volume_l: float | int | None, product: dict[str, Any], *, fruit_kg: float | int | None = None) -> dict[str, Any]:
    """Project a verified dose range using explicit, unit-safe conversions."""
    if not product.get("dose_verified"):
        return {"status": "technical_sheet_required", "minimum": None, "maximum": None, "unit": None}
    low, high = product.get("dose_min"), product.get("dose_max")
    unit = str(product.get("dose_unit") or "").casefold()
    if low is None and high is None:
        return {"status": "technical_sheet_required", "minimum": None, "maximum": None, "unit": None}
    factor, output_unit = None, None
    if unit == "g/hl" and volume_l: factor, output_unit = float(volume_l) / 100, "g"
    elif unit == "ml/hl" and volume_l: factor, output_unit = float(volume_l) / 100, "mL"
    elif unit == "g/l" and volume_l: factor, output_unit = float(volume_l), "g"
    elif unit == "ml/l" and volume_l: factor, output_unit = float(volume_l), "mL"
    elif unit in {"kg/hl", "kg/hl/%vol"} and volume_l: factor, output_unit = float(volume_l) / 100, "kg"
    elif unit in {"g/100kg", "g/100 kg"} and fruit_kg: factor, output_unit = float(fruit_kg) / 100, "g"
    elif unit in {"g/ton", "g/t"} and fruit_kg: factor, output_unit = float(fruit_kg) / 1000, "g"
    if factor is None and not volume_l:
        return {"status": "lot_basis_required", "minimum": None, "maximum": None, "unit": None}
    if factor is None:
        return {"status": "unsupported_unit", "minimum": None, "maximum": None, "unit": None}
    return {"status": "calculated", "minimum": round(float(low if low is not None else high) * factor, 2), "maximum": round(float(high if high is not None else low) * factor, 2), "unit": output_unit, "basis": product.get("dose_basis")}


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


_LAB_CODE_ALIASES = {
    "ph": "ph",
    "total_acidity": "total_acidity",
    "total_acidity_tartaric": "total_acidity",
    "titratable_acidity": "total_acidity",
    "acidita_totale": "total_acidity",
    "potential_alcohol": "potential_alcohol",
    "potential_alc": "potential_alcohol",
    "alcol_potenziale": "potential_alcohol",
    "yan": "yan",
    "apa": "yan",
    "azoto_prontamente_assimilabile_apa_yan": "yan",
    "turbidity": "turbidity",
    "ntu": "turbidity",
    "torbidita": "turbidity",
    "torbidita_ntu": "turbidity",
    "catechins": "catechins",
    "catechine": "catechins",
    "volatile_acidity": "volatile_acidity",
    "acidita_volatile": "volatile_acidity",
    "potassium": "potassium",
    "potassio": "potassium",
    "malic_acid": "malic_acid",
    "acido_malico": "malic_acid",
    "lactic_acid": "lactic_acid",
    "acido_lattico": "lactic_acid",
    "residual_sugar": "residual_sugar",
    "glucose_fructose": "residual_sugar",
    "zuccheri_residui": "residual_sugar",
    "actual_alcohol": "actual_alcohol",
    "alcol_effettivo": "actual_alcohol",
    "alcohol": "actual_alcohol",
    "free_so2": "free_so2",
    "so2_libera": "free_so2",
    "total_so2": "total_so2",
    "so2_totale": "total_so2",
    "dissolved_oxygen": "dissolved_oxygen",
    "ossigeno_disciolto": "dissolved_oxygen",
    "tartaric_acid": "tartaric_acid",
    "acido_tartarico": "tartaric_acid",
    "citric_acid": "citric_acid",
    "acido_citrico": "citric_acid",
    "ammonium_nitrogen": "ammonium_nitrogen",
    "azoto_ammoniacale": "ammonium_nitrogen",
    "alpha_amino_nitrogen": "alpha_amino_nitrogen",
    "azoto_alfa_amminico": "alpha_amino_nitrogen",
    "pan": "alpha_amino_nitrogen",
    "calcium": "calcium", "calcio": "calcium",
    "copper": "copper", "rame": "copper",
    "iron": "iron", "ferro": "iron",
    "acetaldehyde": "acetaldehyde", "acetaldeide": "acetaldehyde",
    "color_intensity": "color_intensity", "intensita_colorante": "color_intensity",
    "color_hue": "color_hue", "tonalita": "color_hue",
    "total_polyphenols": "total_polyphenols", "polifenoli_totali": "total_polyphenols", "tpi": "total_polyphenols", "ipt": "total_polyphenols",
    "anthocyanins": "anthocyanins", "antociani": "anthocyanins",
    "carbon_dioxide": "carbon_dioxide", "co2": "carbon_dioxide",
    "brett": "brettanomyces", "brettanomyces_bruxellensis": "brettanomyces",
    "brettanomyces_count": "brettanomyces", "brettanomyces_qpcr": "brettanomyces",
}


def _normalized_lab_code(code: Any, name: Any = None) -> str:
    raw = str(code or name or "").strip().casefold()
    key = "_".join(re.sub(r"[^a-z0-9]+", " ", "".join(
        character for character in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(character)
    )).split())
    return _LAB_CODE_ALIASES.get(key, key)


def lab_evidence_rows(vintage_year: int) -> list[dict[str, Any]]:
    """Fetch a vintage once so dashboards can group evidence without N+1 queries."""
    return fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_type,s.lab_date,s.sampled_at,s.needs_review,s.wine_lot_id,"
        "(SELECT GROUP_CONCAT(link.wine_lot_id) FROM lab_sample_wine_lots link WHERE link.sample_id=s.id) linked_wine_lot_ids,"
        "v.name variety_name,COALESCE(m.canonical_code,r.analyte_code) analyte_code,COALESCE(m.canonical_name,r.analyte_name) analyte_name,"
        "CASE WHEN r.numeric_value IS NULL THEN NULL ELSE r.numeric_value*COALESCE(m.conversion_multiplier,1) END numeric_value,r.text_value,COALESCE(m.canonical_unit,r.unit) unit,r.flag,"
        "r.analyte_code reported_analyte_code,r.analyte_name reported_analyte_name,r.numeric_value reported_numeric_value,r.unit reported_unit,"
        "(SELECT CONCAT('api/v1/attachments/',ea.id,'/file') FROM entity_attachments ea WHERE ea.estate_id=s.estate_id "
        "AND ea.entity_type='lab_sample' AND ea.entity_id=s.id ORDER BY ea.created_at DESC LIMIT 1) report_url "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN grape_varieties v ON v.id=s.variety_id "
        "JOIN lab_results r ON r.sample_id=s.id LEFT JOIN enology_analyte_mappings m ON m.id=r.analyte_mapping_id AND m.estate_id=s.estate_id WHERE s.estate_id=%s AND s.needs_review=0 "
        "AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date))=%s AND s.sample_type IN ('must','wine','grape') "
        "ORDER BY COALESCE(s.sampled_at,s.lab_date) DESC,s.created_at DESC",
        (estate_id(), vintage_year),
    )


def lot_lab_evidence(
    lot: dict[str, Any], vintage_year: int, *, now: datetime | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return exact-lot laboratory evidence and clearly separated link candidates."""
    now = (now or datetime.now()).replace(tzinfo=None)
    rows = rows if rows is not None else lab_evidence_rows(vintage_year)
    lot_key = normalize_product_name(str(lot.get("variety_summary") or ""))
    lot_id = str(lot.get("id") or "")
    exact = [row for row in rows if str(row.get("wine_lot_id") or "") == lot_id or lot_id in str(row.get("linked_wine_lot_ids") or "").split(",")]
    candidate_rows = [
        row for row in rows
        if str(row.get("wine_lot_id") or "") != lot_id and lot_id not in str(row.get("linked_wine_lot_ids") or "").split(",") and lot_key
        and normalize_product_name(str(row.get("variety_name") or row.get("sample_name") or "")) == lot_key
    ]
    metrics: dict[str, dict[str, Any]] = {}
    for row in exact:
        code = _normalized_lab_code(row.get("analyte_code"), row.get("analyte_name"))
        if code in metrics:
            continue
        stamp = _parse_time(row.get("sampled_at") or row.get("lab_date"))
        age_days = max(0, (now.date() - stamp.date()).days) if stamp else None
        normalized = normalize_enology_measurement(code, row.get("numeric_value"), row.get("unit"))
        metrics[code] = {
            "code": code,
            "name": row.get("analyte_name") or code.replace("_", " ").title(),
            "value": normalized["value"] if normalized["usable"] else (row.get("numeric_value") if row.get("numeric_value") is not None else row.get("text_value")),
            "unit": normalized["unit"] if normalized["usable"] else row.get("unit"),
            "reported_value": row.get("reported_numeric_value") if row.get("reported_numeric_value") is not None else row.get("text_value"),
            "reported_unit": row.get("reported_unit"),
            "reported_analyte_code": row.get("reported_analyte_code"), "reported_analyte_name": row.get("reported_analyte_name"),
            "decision_usable": normalized["usable"],
            "validation_error": normalized["reason"],
            "sample_id": row.get("sample_id"),
            "sample_name": row.get("sample_name"),
            "sample_type": row.get("sample_type"),
            "lab_date": row.get("lab_date"),
            "sampled_at": row.get("sampled_at"),
            "age_days": age_days,
            "flag": row.get("flag"),
            "report_url": row.get("report_url"),
        }
    candidates_by_sample: dict[str, dict[str, Any]] = {}
    for row in candidate_rows:
        sample_id = str(row.get("sample_id") or "")
        if not sample_id:
            continue
        candidate = candidates_by_sample.setdefault(sample_id, {
            "sample_id": sample_id, "sample_name": row.get("sample_name"), "sample_type": row.get("sample_type"),
            "lab_date": row.get("lab_date"), "variety_name": row.get("variety_name"), "report_url": row.get("report_url"),
            "link_required": True, "metrics": {},
        })
        code = _normalized_lab_code(row.get("analyte_code"), row.get("analyte_name"))
        if code not in candidate["metrics"]:
            normalized = normalize_enology_measurement(code, row.get("numeric_value"), row.get("unit"))
            candidate["metrics"][code] = {
                "code": code,
                "name": row.get("analyte_name") or code.replace("_", " ").title(),
                "value": normalized["value"] if normalized["usable"] else (row.get("numeric_value") if row.get("numeric_value") is not None else row.get("text_value")),
                "unit": normalized["unit"] if normalized["usable"] else row.get("unit"),
                "decision_usable": normalized["usable"], "validation_error": normalized["reason"],
            }
    candidates = list(candidates_by_sample.values())
    status = "linked" if metrics else "link_required" if candidates else "missing"
    return {
        "status": status, "checked_at": now, "metrics": metrics,
        "linked_sample_ids": sorted({str(row.get("sample_id")) for row in exact if row.get("sample_id")}),
        "candidates": candidates,
        "policy": "Only results linked to this exact wine lot can unlock dosing; variety matches are shown only as link candidates.",
    }


def lot_with_lab_measurements(lot: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Overlay exact-lot results for decisions without overwriting stored process profiles."""
    metrics = evidence.get("metrics") or {}
    output = dict(lot)
    for metric, field in (("yan", "yan_mg_l"), ("potential_alcohol", "potential_alcohol_pct"), ("turbidity", "must_turbidity_ntu")):
        measurement = metrics.get(metric) or {}
        value = measurement.get("value")
        if value is not None and measurement.get("decision_usable", True):
            output[field] = value
    return output


def additive_prediction_pipeline(
    lot: dict[str, Any], protocols: list[dict[str, Any]], readings: list[dict[str, Any]],
    additions: list[dict[str, Any]], *, products: list[dict[str, Any]] | None = None,
    lab_evidence: dict[str, Any] | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Build a source-backed, enologist-controlled recipe forecast."""
    now = (now or datetime.now()).replace(tzinfo=None)
    color = str(lot.get("wine_color") or "").casefold()
    stage = str(lot.get("process_stage") or lot.get("stage") or "must").casefold()
    valid_density = sorted(
        [(stamp, float(row["density_sg"])) for row in readings if (stamp := _parse_time(row.get("observed_at"))) and row.get("density_sg") is not None],
        key=lambda item: item[0],
    )
    density_start = valid_density[0][1] if valid_density else None
    density_latest = valid_density[-1][1] if valid_density else None
    density_drop_points = round((density_start - density_latest) * 1000, 1) if density_start is not None and density_latest is not None else None
    drop_rate = None
    if len(valid_density) >= 2:
        elapsed_days = (valid_density[-1][0] - valid_density[0][0]).total_seconds() / 86400
        if elapsed_days > 0:
            drop_rate = max(0.0, (valid_density[0][1] - valid_density[-1][1]) * 1000 / elapsed_days)
    valid_babo = sorted(
        [(stamp, float(row["babo"])) for row in readings if (stamp := _parse_time(row.get("observed_at"))) and row.get("babo") is not None],
        key=lambda item: item[0],
    )
    # Progress is anchored to the first accepted must reading. A later high
    # outlier must not move the starting point or product timing window.
    babo_start = valid_babo[0][1] if valid_babo else None
    babo_latest = valid_babo[-1][1] if valid_babo else None
    babo_progress_pct = round(max(0.0, min(100.0, (babo_start - babo_latest) / babo_start * 100)), 1) if babo_start else None
    babo_drop_rate = None
    if len(valid_babo) >= 2:
        elapsed_days = (valid_babo[-1][0] - valid_babo[-2][0]).total_seconds() / 86400
        if elapsed_days > 0:
            babo_drop_rate = max(0.0, (valid_babo[-2][1] - valid_babo[-1][1]) / elapsed_days)
    applied_events = [item for item in additions if item.get("event_status") == "applied"]
    protocol_counts: dict[str, int] = {}
    product_by_id = {str(item.get("id") or ""): item for item in (products or [])}
    for item in protocols:
        key = str(item.get("product_catalog_id") or "")
        protocol_counts[key] = protocol_counts.get(key, 0) + 1
    candidates: list[dict[str, Any]] = []
    for protocol in protocols:
        colors = {item.strip().casefold() for item in str(protocol.get("wine_colors") or "any").split(",")}
        if "any" not in colors and color not in colors:
            continue
        protocol_stages = {
            item.strip().casefold().replace("_", "-")
            for item in str(protocol.get("process_stages") or "").split(",") if item.strip()
        }
        stage_groups = {
            "must": {"receiving", "intake", "must", "pre-fermentation", "inoculation"},
            "fermentation": {"fermentation", "fermenting", "primary-fermentation", "maceration"},
            "malo": {"malo", "malolactic", "post-fermentation"},
            "aging": {"pressing", "pressed", "transfer", "racking", "settling", "clarification", "stabilization", "aging"},
            "bottled": {"bottling", "bottled"},
            "closed": {"closed"},
        }
        active_stages = stage_groups.get(stage.replace("_", "-"), {stage.replace("_", "-")})
        if protocol_stages and not active_stages.intersection(protocol_stages):
            continue
        projection = project_product_quantity(
            lot.get("volume_l") or lot.get("initial_l"),
            {**protocol, "dose_verified": bool(protocol.get("dose_unit"))},
            fruit_kg=lot.get("fruit_kg"),
        )
        blockers: list[str] = []
        advisory: list[str] = []
        if projection["status"] != "calculated":
            if projection["status"] == "technical_sheet_required" and not protocol.get("dose_unit"):
                blockers.append("Record the enologist-selected bench-trial rate; this product has no default dose in the system.")
            else:
                blockers.append("Record the lot volume or grape weight required by this product-sheet dose.")
        required_labs = [item.strip() for item in str(protocol.get("required_lab_analytes") or "").split(",") if item.strip()]
        trigger = str(protocol.get("trigger_code") or "")
        used_labs: list[dict[str, Any]] = []
        if lab_evidence is not None:
            metrics = lab_evidence.get("metrics") or {}
            max_age = int(protocol.get("lab_max_age_days") or 0)
            for code in required_labs:
                evidence = metrics.get(code)
                if not evidence:
                    message = f"Link a current {code.replace('_', ' ')} laboratory result to this exact wine lot."
                    if trigger == "density_drop_30" and code == "turbidity":
                        advisory.append(message)
                    else:
                        blockers.append(message)
                    continue
                used_labs.append(evidence)
                if max_age and evidence.get("age_days") is not None and int(evidence["age_days"]) > max_age:
                    advisory.append(f"Consider repeating {code.replace('_', ' ')}: the linked result is {evidence['age_days']} days old (working freshness target {max_age}).")
        timing_status, timing_detail, predicted_for = "future", "Not yet at the product-sheet timing gate.", None
        if trigger == "inoculation":
            if lot.get("yan_mg_l") is None: blockers.append("Measure YAN/APA before the inoculation and nutrient plan.")
            if lot.get("potential_alcohol_pct") is None: blockers.append("Record calculated potential alcohol before choosing the yeast working rate.")
            is_nutrient = str(protocol.get("product_class") or "").casefold() == "nutrient"
            yan_sufficient = lot.get("yan_mg_l") is not None and float(lot.get("yan_mg_l")) >= float(lot.get("yan_target_mg_l") or 150)
            if is_nutrient and yan_sufficient:
                timing_status = "not_indicated"
                timing_detail = "Recorded YAN/APA already meets the working target; this inoculation nutrient is not currently indicated."
            else:
                timing_status = "due" if stage in {"must", "pre-fermentation"} else "future"
                timing_detail = "Inoculation window is active now." if timing_status == "due" else "This inoculation window is not current."
        elif trigger == "alcohol_consistency":
            if lot.get("potential_alcohol_pct") is None:
                blockers.append("Record current potential alcohol from Babo/calculation or an exact-lot laboratory result.")
            if lot.get("target_potential_alcohol_pct") is None:
                blockers.append("Set the estate target potential alcohol for this lot so split lots can be held to one target.")
            timing_status = "due" if stage in {"receiving", "must", "pre-fermentation", "fermentation"} else "future"
            timing_detail = "Calculate the rectified grape-must quantity now from measured potential alcohol, verified volume and the estate target." if timing_status == "due" else "Alcohol-consistency enrichment is only calculated during the active must/fermentation window."
            advisory.append("Compliance warning only: confirm the current vintage and denomination rules before use; the technical quantity remains visible.")
        elif trigger == "pressing":
            timing_status = "due" if stage in {"receiving", "pressing", "must"} else "future"
            timing_detail = "Add uniformly to the juice after pressing for settling or flotation." if timing_status == "due" else "The post-press clarification-enzyme window has passed or is not active."
        elif trigger == "crusher_or_fermentation":
            if str(protocol.get("protocol_code") or "") == "sound_must" and str(lot.get("fruit_condition") or "unknown").casefold() == "unknown":
                blockers.append("Record whether the fruit is sound or mold-affected before choosing the tannin range.")
            timing_status = "due" if stage in {"receiving", "must", "fermentation"} else "future"
            timing_detail = "Crusher/maceration window is active; confirm fruit condition and exact rate." if timing_status == "due" else "Extraction-enzyme window is not current."
        elif trigger in {"pump_over", "first_pump_over"}:
            timing_status = "due" if stage == "fermentation" else "future"
            timing_detail = "Confirm the applicable pump-over and selected purpose with the enologist." if timing_status == "due" else "Waiting for the alcoholic-fermentation pump-over window."
        elif trigger == "density_drop_30":
            if lot.get("yan_mg_l") is None: blockers.append("Measure YAN/APA; nutrient quantity cannot be selected from a deficit assumption.")
            if lot.get("potential_alcohol_pct") is None: blockers.append("Record potential alcohol for the nutrient decision.")
            if lot.get("must_turbidity_ntu") is None: advisory.append("Confirm must turbidity when available; the current recommendation uses YAN/APA, potential alcohol and fermentation progress.")
            if density_drop_points is None and babo_progress_pct is None:
                blockers.append("Record at least two dated density or Babo readings.")
                timing_detail = "Waiting for density or Babo evidence for the first-third fermentation gate."
            elif density_drop_points is not None and density_drop_points >= 30:
                timing_status, timing_detail = "due", f"Density has fallen about {density_drop_points:g} points; the first-third review gate is active."
            elif babo_progress_pct is not None and 25 <= babo_progress_pct <= 45:
                timing_status, timing_detail = "due", f"Babo has fallen from {babo_start:g} to {babo_latest:g} ({babo_progress_pct:g}% apparent progress); the first-third nutrition window is active."
            elif babo_progress_pct is not None and babo_progress_pct > 45:
                timing_status, timing_detail = "past", f"Babo has fallen from {babo_start:g} to {babo_latest:g} ({babo_progress_pct:g}% apparent progress); the routine first-third nutrition window has passed."
            elif drop_rate and drop_rate > 0:
                remaining_days = max(0.0, (30 - density_drop_points) / drop_rate)
                predicted_for = now + timedelta(days=remaining_days)
                timing_status, timing_detail = "predicted", f"About {30-density_drop_points:g} density points remain to the product-sheet timing gate."
            else:
                timing_detail = "Density is not falling enough to forecast the 30-point gate."
        elif trigger == "sanitary_evidence":
            laccase = lot.get("laccase_u_ml")
            affected = str(lot.get("fruit_condition") or "unknown").casefold() in {"botrytis", "infected"}
            if laccase is None and not affected:
                blockers.append("Record Botrytis/fruit condition or measured laccase evidence before this use case.")
            timing_status = "due" if affected or (laccase is not None and float(laccase) > 2) else "future"
            timing_detail = "Sanitary evidence supports immediate enologist review." if timing_status == "due" else "No qualifying sanitary trigger is recorded."
        elif trigger == "ageing_review":
            filtration = _parse_time(lot.get("planned_filtration_at"))
            if not filtration:
                blockers.append("Record the planned filtration date to protect the minimum contact time.")
            else:
                predicted_for = filtration - timedelta(hours=float(protocol.get("minimum_contact_hours") or 0))
                timing_status = "due" if now >= predicted_for and stage == "aging" else "predicted"
                timing_detail = "Review now to preserve the minimum pre-filtration contact time." if timing_status == "due" else "Forecast from the planned filtration date and required contact time."
            advisory.append("Run and record a sensory bench trial before an ageing treatment.")
        elif trigger == "bench_trial":
            timing_status = "due" if stage in {"must", "wine", "aging", "clarification", "post-fermentation"} else "future"
            timing_detail = "The product is eligible for a progressive laboratory/sensory bench trial; no cellar dose is selected yet." if timing_status == "due" else "Waiting for the applicable must/wine fining stage."
            blockers.append("Run and record a progressive bench trial, including the selected exact rate and outcome.")
        elif trigger == "sluggish_fermentation":
            trajectory_rate = drop_rate if drop_rate is not None else babo_drop_rate
            trajectory_unit = "density points/day" if drop_rate is not None else "Babo/day"
            if len(valid_density) < 2 and len(valid_babo) < 2:
                blockers.append("Record at least two dated density or Babo readings before diagnosing sluggish or stuck fermentation.")
                timing_detail = "Waiting for a supported fermentation trajectory."
            elif stage != "fermentation":
                timing_detail = "Corrective nutrient protocol is only relevant during alcoholic fermentation."
            elif trajectory_rate is not None and trajectory_rate <= (2 if drop_rate is not None else 0.5):
                timing_status = "due"
                timing_detail = f"Fermentation is falling only {trajectory_rate:g} {trajectory_unit}; the corrective protocol may be indicated."
            else:
                timing_status = "not_indicated"
                timing_detail = f"The active trajectory ({trajectory_rate:g} {trajectory_unit}) does not support a sluggish/stuck correction." if trajectory_rate is not None else "Fermentation trajectory is not conclusive."
        elif trigger == "acidification_bench_trial":
            timing_status = "due" if stage in {"must", "fermentation", "wine", "aging"} else "future"
            timing_detail = "Current pH and total acidity can support an acidification bench trial; the enologist must define the target and rate." if timing_status == "due" else "Acidification review is not at an active must/wine stage."
            blockers.append("Record the selected acidification bench-trial rate in g/L and confirm the applicable legal limit.")
        elif trigger == "mlf_inoculation":
            timing_status = "due" if stage in {"fermentation", "post-fermentation", "wine", "aging"} else "future"
            timing_detail = "Review MLF feasibility, exact sachet coverage and inoculation timing now." if timing_status == "due" else "The malolactic-inoculation window is not current."
            blockers.append("Record the exact sachet coverage and selected co-inoculation or sequential MLF plan.")
            advisory.append("Monitor malic acid every 2-4 days and confirm completion before stabilization.")
        elif trigger == "pre_bottling_bench":
            timing_status = "due" if stage in {"wine", "aging", "clarification", "post-fermentation", "pre-bottling", "bottling"} else "future"
            timing_detail = "A progressive sensory and stability trial can be scheduled for the pre-bottling decision." if timing_status == "due" else "Waiting for the wine-aging or pre-bottling stage."
            blockers.append("Record the progressive bench-trial result, selected exact rate and required stability checks.")
        elif trigger == "tirage":
            timing_status = "due" if stage in {"tirage", "sparkling", "secondary-fermentation"} else "future"
            timing_detail = "The traditional-method tirage window is active." if timing_status == "due" else "This protocol is reserved for a recorded traditional-method tirage plan."
            blockers.append("Record the tirage plan and current base-wine chemistry before selecting this product.")
        elif trigger == "must_clarification":
            timing_status = "due" if stage in {"pressing", "must", "clarification"} else "future"
            timing_detail = "Must clarification is active; select the temperature/settling-time rate and plan the pectin test." if timing_status == "due" else "The must-clarification window is not current."
            blockers.append("Record must temperature, turbidity and the post-treatment pectin-test result.")
        elif trigger == "clarification_enzyme":
            timing_status = "due" if stage in {"fermentation", "post-fermentation", "clarification", "aging"} else "future"
            timing_detail = "The clarification/filterability enzyme window is active; preserve the product-sheet contact time before filtration." if timing_status == "due" else "Waiting for the applicable fermentation or post-fermentation clarification stage."
            filtration = _parse_time(lot.get("planned_filtration_at"))
            contact_hours = float(protocol.get("minimum_contact_hours") or 0)
            if filtration and contact_hours:
                latest_addition = filtration - timedelta(hours=contact_hours)
                predicted_for = latest_addition
                if now > latest_addition:
                    blockers.append("The planned filtration date does not leave the verified minimum enzyme contact time.")
            elif contact_hours:
                advisory.append("Record the planned filtration date to verify the minimum enzyme contact time.")
        elif trigger == "mlf_activation":
            timing_status = "due" if stage in {"fermentation", "post-fermentation", "wine", "aging"} else "future"
            timing_detail = "The MLF activation review is active; confirm feasibility and the selected bacteria timing." if timing_status == "due" else "Waiting for the supported malolactic-fermentation window."
            advisory.append("Monitor malic acid every 2-4 days and confirm completion before stabilization.")
        elif trigger == "microbial_control":
            timing_status = "due" if stage in {"post-fermentation", "wine", "aging", "clarification"} else "future"
            timing_detail = "A linked microbiology result supports review of this post-fermentation control protocol." if timing_status == "due" else "This protocol is reserved for post-fermentation wine with laboratory evidence."
            advisory.append("Repeat the relevant microbiology test after the product-sheet contact period and record the result.")
        elif trigger == "lees_ageing":
            timing_status = "due" if stage in {"wine", "aging"} else "future"
            timing_detail = "Lees-aging review is active; confirm temperature, contact time and stirring controls." if timing_status == "due" else "Waiting for the wine-aging stage."
            blockers.append("Record the lees-aging plan and sensory trial before treatment.")
        matching_applied = [item for item in applied_events if normalize_product_name(str(item.get("additive_name") or "")) == normalize_product_name(str(protocol.get("product_name") or ""))]
        protocol_applied = trigger != "alcohol_consistency" and bool(matching_applied) and (
            protocol_counts.get(str(protocol.get("product_catalog_id") or ""), 0) <= 1
            or any(str(protocol.get("protocol_code") or "").casefold() in str(item.get("reason_text") or "").casefold() or str(protocol.get("protocol_name") or "").casefold() in str(item.get("reason_text") or "").casefold() for item in matching_applied)
        )
        matching_planned = [item for item in additions if item.get("event_status") == "planned" and normalize_product_name(str(item.get("additive_name") or "")) == normalize_product_name(str(protocol.get("product_name") or ""))]
        if protocol_applied:
            decision_status = "applied"
        elif blockers:
            decision_status = "blocked"
        elif timing_status == "due":
            decision_status = "review_due"
        else:
            decision_status = "forecast"
        if protocol_applied:
            operational_status = "applied"
        elif matching_planned:
            operational_status = "planned_recorded"
        elif timing_status == "due" and blockers:
            operational_status = "data_needed"
        elif timing_status == "due":
            operational_status = "recommended_now"
        elif timing_status == "past":
            operational_status = "timing_passed"
        elif timing_status == "not_indicated":
            operational_status = "not_indicated"
        elif timing_status == "predicted":
            operational_status = "upcoming"
        else:
            operational_status = "not_current"
        dose_recommendation = working_dose_recommendation(lot, protocol, projection, readings, blockers, timing_status, additions, lab_evidence)
        if trigger == "alcohol_consistency" and dose_recommendation.get("status") == "not_indicated":
            decision_status = "forecast"
            operational_status = "not_indicated"
        catalog_product = product_by_id.get(str(protocol.get("product_catalog_id") or "")) or {}
        candidates.append({
            **protocol, "projection": projection, "decision_status": decision_status, "operational_status": operational_status,
            "in_cellar": bool(catalog_product.get("in_cellar")), "stock": catalog_product.get("stock") or [],
            "timing_status": timing_status, "timing_detail": timing_detail,
            "predicted_for": predicted_for, "blockers": blockers, "advisory": advisory,
            "required_lab_analytes": required_labs, "lab_evidence_used": used_labs,
            "lab_evidence_status": (lab_evidence or {}).get("status") if lab_evidence is not None else "not_checked",
            "lab_candidates": (lab_evidence or {}).get("candidates", []) if lab_evidence is not None else [],
            "density_drop_points": density_drop_points,
            "babo_start": babo_start, "babo_latest": babo_latest, "babo_progress_pct": babo_progress_pct,
            "confidence": "medium" if projection["status"] == "calculated" and not blockers else "low",
            "working_recommendation": dose_recommendation,
            "approval_required": False, "operator_record_is_authoritative": True, "automatic_instruction": False,
        })
    covered_products = {str(item.get("product_catalog_id") or "") for item in protocols}
    for product in suggest_products(lot, products or []):
        if str(product.get("id") or "") in covered_products:
            continue
        candidates.append({
            **product, "id": f"pending:{product.get('id')}", "product_catalog_id": product.get("id"),
            "protocol_name": "Protocol verification pending", "purpose": product.get("description") or "Candidate product",
            "decision_status": "blocked", "timing_status": "future", "timing_detail": "No purpose-specific protocol has been verified for this product yet.",
            "predicted_for": None, "blockers": ["Verify dosage, timing, preparation, prerequisites and constraints from the current product data sheet."],
            "advisory": [], "projection": {"status": "technical_sheet_required", "minimum": None, "maximum": None, "unit": None},
            "confidence": "low", "approval_required": False, "operator_record_is_authoritative": True, "automatic_instruction": False,
        })
    priority = {"review_due": 0, "blocked": 1, "forecast": 2, "applied": 3}
    candidates.sort(key=lambda item: (priority.get(item["decision_status"], 9), str(item.get("predicted_for") or "9999"), str(item.get("product_name"))))
    due = sum(item["decision_status"] == "review_due" for item in candidates)
    blocked = sum(item["decision_status"] == "blocked" for item in candidates)
    batch_recipe = []
    for item in candidates:
        if not item.get("in_cellar") or str(item.get("id") or "").startswith("pending:"):
            continue
        product_class = str(item.get("product_class") or "other")
        selection_group = "choose_one_yeast" if product_class == "yeast" else "conditional_mlf" if product_class == "bacteria" else "conditional_nutrition" if product_class == "nutrient" else "purpose_specific_fining" if product_class == "fining" else "purpose_specific_additive"
        batch_recipe.append({
            "id": item.get("id"), "product_catalog_id": item.get("product_catalog_id"),
            "manufacturer": item.get("manufacturer"), "product_name": item.get("product_name"),
            "product_class": product_class, "protocol_name": item.get("protocol_name"),
            "selection_group": selection_group, "decision_status": item.get("decision_status"),
            "operational_status": item.get("operational_status"),
            "projection": item.get("projection"), "timing_detail": item.get("timing_detail"),
            "preparation": item.get("preparation"), "application_instructions": item.get("application_instructions"),
            "blockers": item.get("blockers") or [], "stock": item.get("stock") or [],
            "not_a_combined_instruction": True,
        })
    recipe_candidates = [item for item in candidates if not str(item.get("id") or "").startswith("pending:")]
    manufacturer_recipes = []
    for manufacturer in sorted({str(item.get("manufacturer") or "Unknown") for item in recipe_candidates}):
        alternatives = [item for item in recipe_candidates if str(item.get("manufacturer") or "Unknown") == manufacturer]
        chosen_by_product: dict[str, dict[str, Any]] = {}
        for item in alternatives:
            product_key = str(item.get("product_catalog_id") or item.get("product_name") or "")
            current = chosen_by_product.get(product_key)
            rank = (0 if item.get("decision_status") == "review_due" else 1 if item.get("decision_status") == "blocked" else 2, len(item.get("blockers") or []))
            current_rank = (9, 999) if current is None else (0 if current.get("decision_status") == "review_due" else 1 if current.get("decision_status") == "blocked" else 2, len(current.get("blockers") or []))
            if current is None or rank < current_rank:
                chosen_by_product[product_key] = item
        recipe_items = []
        score = 0
        for item in chosen_by_product.values():
            score += 30 if item.get("decision_status") == "review_due" else 10 if item.get("decision_status") == "forecast" else 0
            score += 12 if item.get("in_cellar") else 0
            score += 6 if (item.get("projection") or {}).get("status") == "calculated" else 0
            score -= 3 * len(item.get("blockers") or [])
            recipe_items.append({
                "id": item.get("id"), "manufacturer": manufacturer, "product_name": item.get("product_name"),
                "product_class": item.get("product_class"), "protocol_name": item.get("protocol_name"),
                "decision_status": item.get("decision_status"), "operational_status": item.get("operational_status"), "projection": item.get("projection"),
                "timing_detail": item.get("timing_detail"), "preparation": item.get("preparation"),
                "application_instructions": item.get("application_instructions"), "advisory": item.get("advisory") or [],
                "pds_url": item.get("pds_url"), "blockers": item.get("blockers") or [], "stock": item.get("stock") or [],
                "working_recommendation": item.get("working_recommendation"),
                "in_cellar": bool(item.get("in_cellar")),
            })
        recipe_items.sort(key=lambda item: ({"yeast": 0, "bacteria": 1, "enzyme": 2, "yeast_derivative": 3, "nutrient": 4, "tannin": 5, "fining": 6, "stabilizer": 7, "treatment": 8}.get(str(item.get("product_class")), 9), str(item.get("product_name"))))
        manufacturer_recipes.append({
            "manufacturer": manufacturer, "evidence_fit_score": score, "items": recipe_items,
            "ready_count": sum(item.get("decision_status") == "review_due" for item in recipe_items),
            "blocked_count": sum(bool(item.get("blockers")) for item in recipe_items),
            "in_cellar_count": sum(bool(item.get("in_cellar")) for item in recipe_items),
            "comparison_basis": "Current lot color/stage, exact-lot laboratory gates, verified dose projection, timing and recorded cellar stock.",
        })
    manufacturer_recipes.sort(key=lambda item: (-item["evidence_fit_score"], item["manufacturer"]))
    best_fit_manufacturer = manufacturer_recipes[0]["manufacturer"] if manufacturer_recipes else None
    return {
        "model_version": ADDITIVE_PREDICTION_MODEL, "predicted_at": now,
        "status": "recommendations_ready" if due else "inputs_needed" if blocked else "monitoring",
        "due_count": due, "blocked_count": blocked, "density_drop_points": density_drop_points,
        "density_drop_rate_points_per_day": round(drop_rate, 1) if drop_rate is not None else None,
        "babo_start": babo_start, "babo_latest": babo_latest, "babo_progress_pct": babo_progress_pct,
        "decisions": candidates, "batch_recipe": batch_recipe, "manufacturer_recipes": manufacturer_recipes,
        "best_fit_manufacturer": best_fit_manufacturer,
        "policy": "This is an operator-ready enology recipe. Lab arrivals and tank readings recalculate timing and quantities immediately. The authenticated enology operator records the action directly; choose-one alternatives and conditional products are never summed automatically.",
    }


def suggest_products(lot: dict[str, Any], products: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Rank official products as lot-specific recommendations."""
    color = str(lot.get("wine_color") or "").casefold()
    context = " ".join(str(lot.get(key) or "") for key in ("target_style", "variety_summary", "stage")).casefold()
    yan = lot.get("yan_mg_l")
    target = float(lot.get("yan_target_mg_l") or 150)
    useful = {"yeast", "yeast_derivative", "enzyme", "bacteria", "nutrient", "tannin", "fining", "stabilizer", "treatment", "oak", "preservation"}
    ranked = []
    for product in products:
        if product.get("product_class") not in useful:
            continue
        colors = {item.strip().casefold() for item in str(product.get("wine_colors") or "any").split(",")}
        if colors and "any" not in colors and color not in colors:
            continue
        description = str(product.get("description") or "").casefold()
        score, reasons = 1, [f"Official {product.get('manufacturer') or 'manufacturer'} {product.get('range_name') or product.get('product_class')} catalog entry"]
        if product.get("in_cellar"):
            score += 4
            reasons.append("photo-confirmed in the 2026 cellar inventory; stock does not itself justify use")
        if color and color in description:
            score += 3; reasons.append(f"described for {color} wine")
        for token in {word for word in re.findall(r"[a-zà-ÿ]{4,}", context) if word not in {"wine", "wines", "stage"}}:
            if token in description:
                score += 2; reasons.append(f"matches {token}")
        if product.get("product_class") == "nutrient":
            if yan is None:
                reasons.append("blocked until YAN/APA is measured")
                score -= 2
            elif float(yan) < target:
                reasons.append(f"YAN/APA is {target - float(yan):g} mg/L below the working target")
                score += 3
            else:
                continue
        projection = project_product_quantity(lot.get("volume_l") or lot.get("initial_l"), product, fruit_kg=lot.get("fruit_kg"))
        ranked.append({**product, "suggestion_score": score, "suggestion_reason": "; ".join(dict.fromkeys(reasons)), "projection": projection, "recommendation_status": "recommended_candidate", "approval_required": False, "is_automatic_instruction": False})
    ranked.sort(key=lambda row: (-row["suggestion_score"], str(row.get("range_name")), str(row.get("product_name"))))
    return ranked[:limit]


def refresh_enology_additive_predictions() -> dict[str, Any]:
    """Persist an auditable current prediction snapshot for every active cellar lot."""
    # New laboratory vocabulary is mapped before any result is allowed to
    # influence the refreshed decision snapshots. Mapping failures remain
    # visible as unmapped evidence and never stop the cellar refresh.
    try:
        from .lab_analyte_mapping import refresh_unmapped_lab_analytes
        refresh_unmapped_lab_analytes()
    except Exception:
        pass
    lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,cp.manual_stage process_stage,w.volume_l,w.fruit_kg,w.initial_l,w.variety_summary,s.vintage_year,p.wine_color,p.target_style,"
        "p.yan_mg_l,p.yan_target_mg_l,p.potential_alcohol_pct,p.target_potential_alcohol_pct,p.must_turbidity_ntu,p.fruit_condition,p.laccase_u_ml,"
        "p.anthocyanin_tannin_ratio,p.inoculated_at,p.planned_filtration_at "
        "FROM wine_lots w JOIN seasons s ON s.id=w.season_id LEFT JOIN cellar_control_profiles cp ON cp.container_id=w.current_container_id AND cp.estate_id=w.estate_id LEFT JOIN enology_process_profiles p ON p.wine_lot_id=w.id AND p.estate_id=w.estate_id "
        "WHERE w.estate_id=%s AND w.stage NOT IN ('bottled','closed') ORDER BY w.started_at,w.code",
        (estate_id(),),
    )
    protocols, products = protocol_rows(), catalog_rows()
    all_readings = fetch_all(
        "SELECT wine_lot_id,observed_at,density_sg,brix,babo,temp_c,ph FROM fermentation_observations "
        "WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE estate_id=%s AND stage NOT IN ('bottled','closed')) ORDER BY wine_lot_id,observed_at",
        (estate_id(), estate_id()),
    )
    all_additions = fetch_all(
        "SELECT wine_lot_id,additive_name,event_status,applied_at,quantity,unit,reason_text FROM enology_addition_events "
        "WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE estate_id=%s AND stage NOT IN ('bottled','closed'))",
        (estate_id(), estate_id()),
    )
    readings_by_lot: dict[str, list[dict[str, Any]]] = {}
    additions_by_lot: dict[str, list[dict[str, Any]]] = {}
    for row in all_readings:
        readings_by_lot.setdefault(str(row.get("wine_lot_id")), []).append(row)
    for row in all_additions:
        additions_by_lot.setdefault(str(row.get("wine_lot_id")), []).append(row)
    evidence_rows_by_year = {year: lab_evidence_rows(year) for year in {int(lot["vintage_year"]) for lot in lots}}
    saved, due, blocked = 0, 0, 0
    with transaction() as (_, cursor):
        for lot in lots:
            lot_id = str(lot["id"])
            readings = readings_by_lot.get(lot_id, [])
            additions = additions_by_lot.get(lot_id, [])
            year = int(lot["vintage_year"])
            lab_evidence = lot_lab_evidence(lot, year, rows=evidence_rows_by_year[year])
            decision_lot = lot_with_lab_measurements(lot, lab_evidence)
            pipeline = additive_prediction_pipeline(decision_lot, protocols, readings, additions, products=products, lab_evidence=lab_evidence)
            signature_payload = {
                "model": ADDITIVE_PREDICTION_MODEL, "lot": decision_lot, "readings": readings,
                "additions": additions, "labs": lab_evidence.get("metrics"),
                "protocols": [(row.get("id"), row.get("source_revision"), row.get("verified_on")) for row in protocols],
            }
            input_signature = hashlib.sha256(json.dumps(json_ready(signature_payload), sort_keys=True, default=str).encode()).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO enology_additive_prediction_snapshots (id,estate_id,wine_lot_id,model_version,input_signature,prediction_status,due_count,blocked_count,pipeline_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_id(), estate_id(), lot["id"], ADDITIVE_PREDICTION_MODEL, input_signature, pipeline["status"], pipeline["due_count"], pipeline["blocked_count"], json.dumps(json_ready(pipeline))),
            )
            saved += int(cursor.rowcount > 0)
            due += pipeline["due_count"]
            blocked += pipeline["blocked_count"]
        cursor.execute("DELETE FROM enology_additive_prediction_snapshots WHERE estate_id=%s AND predicted_at<NOW()-INTERVAL 90 DAY", (estate_id(),))
    return {"status": "processed", "lots": len(lots), "snapshots_saved": saved, "review_due": due, "blocked": blocked, "model_version": ADDITIVE_PREDICTION_MODEL}
