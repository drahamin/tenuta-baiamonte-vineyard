"""Official LAFFORT product catalog and guarded enology suggestions."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import unescape
import json
import re
import unicodedata
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..db import fetch_all, transaction
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


ADDITIVE_PREDICTION_MODEL = "enology-additive-decisions-v2-lab-gated"


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
    elif unit == "kg/hl" and volume_l: factor, output_unit = float(volume_l) / 100, "kg"
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
    "torbidita": "turbidity",
    "catechins": "catechins",
    "catechine": "catechins",
    "volatile_acidity": "volatile_acidity",
    "acidita_volatile": "volatile_acidity",
    "potassium": "potassium",
    "potassio": "potassium",
    "malic_acid": "malic_acid",
    "acido_malico": "malic_acid",
    "residual_sugar": "residual_sugar",
    "zuccheri_residui": "residual_sugar",
    "free_so2": "free_so2",
    "so2_libera": "free_so2",
    "total_so2": "total_so2",
    "so2_totale": "total_so2",
}


def _normalized_lab_code(code: Any, name: Any = None) -> str:
    raw = str(code or name or "").strip().casefold()
    key = "_".join(re.sub(r"[^a-z0-9]+", " ", "".join(
        character for character in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(character)
    )).split())
    return _LAB_CODE_ALIASES.get(key, key)


def lot_lab_evidence(lot: dict[str, Any], vintage_year: int, *, now: datetime | None = None) -> dict[str, Any]:
    """Return exact-lot laboratory evidence and clearly separated link candidates."""
    now = (now or datetime.now()).replace(tzinfo=None)
    rows = fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_type,s.lab_date,s.sampled_at,s.needs_review,s.wine_lot_id,"
        "v.name variety_name,r.analyte_code,r.analyte_name,r.numeric_value,r.text_value,r.unit,r.flag,"
        "(SELECT CONCAT('api/v1/attachments/',ea.id,'/file') FROM entity_attachments ea WHERE ea.estate_id=s.estate_id "
        "AND ea.entity_type='lab_sample' AND ea.entity_id=s.id ORDER BY ea.created_at DESC LIMIT 1) report_url "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN grape_varieties v ON v.id=s.variety_id "
        "JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s AND s.needs_review=0 "
        "AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date))=%s AND s.sample_type IN ('must','wine','grape') "
        "ORDER BY COALESCE(s.sampled_at,s.lab_date) DESC,s.created_at DESC",
        (estate_id(), vintage_year),
    )
    lot_key = normalize_product_name(str(lot.get("variety_summary") or ""))
    exact = [row for row in rows if str(row.get("wine_lot_id") or "") == str(lot.get("id") or "")]
    candidate_rows = [
        row for row in rows
        if not row.get("wine_lot_id") and lot_key
        and normalize_product_name(str(row.get("variety_name") or row.get("sample_name") or "")) == lot_key
    ]
    metrics: dict[str, dict[str, Any]] = {}
    for row in exact:
        code = _normalized_lab_code(row.get("analyte_code"), row.get("analyte_name"))
        if code in metrics:
            continue
        stamp = _parse_time(row.get("sampled_at") or row.get("lab_date"))
        age_days = max(0, (now.date() - stamp.date()).days) if stamp else None
        metrics[code] = {
            "code": code,
            "name": row.get("analyte_name") or code.replace("_", " ").title(),
            "value": row.get("numeric_value") if row.get("numeric_value") is not None else row.get("text_value"),
            "unit": row.get("unit"),
            "sample_id": row.get("sample_id"),
            "sample_name": row.get("sample_name"),
            "sample_type": row.get("sample_type"),
            "lab_date": row.get("lab_date"),
            "age_days": age_days,
            "flag": row.get("flag"),
            "report_url": row.get("report_url"),
        }
    candidates: list[dict[str, Any]] = []
    seen_samples: set[str] = set()
    for row in candidate_rows:
        sample_id = str(row.get("sample_id") or "")
        if not sample_id or sample_id in seen_samples:
            continue
        seen_samples.add(sample_id)
        candidates.append({
            "sample_id": sample_id, "sample_name": row.get("sample_name"), "sample_type": row.get("sample_type"),
            "lab_date": row.get("lab_date"), "variety_name": row.get("variety_name"), "report_url": row.get("report_url"),
            "link_required": True,
        })
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
        value = (metrics.get(metric) or {}).get("value")
        if value is not None:
            output[field] = value
    return output


def additive_prediction_pipeline(
    lot: dict[str, Any], protocols: list[dict[str, Any]], readings: list[dict[str, Any]],
    additions: list[dict[str, Any]], *, products: list[dict[str, Any]] | None = None,
    lab_evidence: dict[str, Any] | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Build a source-backed recipe forecast; every result remains a review decision."""
    now = (now or datetime.now()).replace(tzinfo=None)
    color = str(lot.get("wine_color") or "").casefold()
    stage = str(lot.get("stage") or "must").casefold()
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
        used_labs: list[dict[str, Any]] = []
        if lab_evidence is not None:
            metrics = lab_evidence.get("metrics") or {}
            max_age = int(protocol.get("lab_max_age_days") or 0)
            for code in required_labs:
                evidence = metrics.get(code)
                if not evidence:
                    blockers.append(f"Link a current {code.replace('_', ' ')} laboratory result to this exact wine lot.")
                    continue
                used_labs.append(evidence)
                if max_age and evidence.get("age_days") is not None and int(evidence["age_days"]) > max_age:
                    blockers.append(f"Repeat {code.replace('_', ' ')}: the linked result is {evidence['age_days']} days old (limit {max_age}).")
        trigger = str(protocol.get("trigger_code") or "")
        timing_status, timing_detail, predicted_for = "future", "Not yet at the product-sheet timing gate.", None
        if trigger == "inoculation":
            if lot.get("yan_mg_l") is None: blockers.append("Measure YAN/APA before the inoculation and nutrient plan.")
            if lot.get("potential_alcohol_pct") is None: blockers.append("Record calculated potential alcohol before yeast approval.")
            timing_status = "due" if stage in {"must", "pre-fermentation"} else "future"
            timing_detail = "Review for inoculation now." if timing_status == "due" else "This inoculation window is not current."
        elif trigger == "pressing":
            timing_status = "due" if stage in {"receiving", "pressing", "must"} else "future"
            timing_detail = "Use as early as possible before pressing, after fruit-condition review." if timing_status == "due" else "Pre-press timing has passed or is not yet active."
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
            if lot.get("must_turbidity_ntu") is None: blockers.append("Record must turbidity for the nutrient decision.")
            if density_drop_points is None:
                blockers.append("Record at least one baseline and current density reading.")
                timing_detail = "Waiting for density evidence for the first-third fermentation gate."
            elif density_drop_points >= 30:
                timing_status, timing_detail = "due", f"Density has fallen about {density_drop_points:g} points; the first-third review gate is active."
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
            if len(valid_density) < 2:
                blockers.append("Record at least two dated density readings before diagnosing sluggish or stuck fermentation.")
                timing_detail = "Waiting for a supported fermentation trajectory."
            elif stage != "fermentation":
                timing_detail = "Corrective nutrient protocol is only relevant during alcoholic fermentation."
            elif drop_rate is not None and drop_rate <= 2:
                timing_status = "due"
                timing_detail = f"Density is falling only {drop_rate:g} points/day; review for a documented sluggish/stuck condition."
            else:
                timing_detail = f"Density trajectory ({drop_rate:g} points/day) does not support the corrective protocol." if drop_rate is not None else "Density trajectory is not conclusive."
        elif trigger == "acidification_bench_trial":
            timing_status = "due" if stage in {"must", "fermentation", "wine", "aging"} else "future"
            timing_detail = "Current pH and total acidity can support an acidification bench trial; the enologist must define the target and rate." if timing_status == "due" else "Acidification review is not at an active must/wine stage."
            blockers.append("Record the approved acidification bench-trial rate in g/L and confirm the applicable legal limit.")
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
            timing_detail = "The traditional-method tirage review gate is active." if timing_status == "due" else "This protocol is reserved for an approved traditional-method tirage plan."
            blockers.append("Record an approved tirage plan and current base-wine chemistry before selecting this product.")
        elif trigger == "must_clarification":
            timing_status = "due" if stage in {"pressing", "must", "clarification"} else "future"
            timing_detail = "Must clarification is active; select the temperature/settling-time rate and plan the pectin test." if timing_status == "due" else "The must-clarification window is not current."
            blockers.append("Record must temperature, turbidity and the post-treatment pectin-test result.")
        elif trigger == "lees_ageing":
            timing_status = "due" if stage in {"wine", "aging"} else "future"
            timing_detail = "Lees-aging review is active; confirm temperature, contact time and stirring controls." if timing_status == "due" else "Waiting for the wine-aging stage."
            blockers.append("Record the approved lees-aging plan and sensory trial before treatment.")
        matching_applied = [item for item in applied_events if normalize_product_name(str(item.get("additive_name") or "")) == normalize_product_name(str(protocol.get("product_name") or ""))]
        protocol_applied = bool(matching_applied) and (
            protocol_counts.get(str(protocol.get("product_catalog_id") or ""), 0) <= 1
            or any(str(protocol.get("protocol_code") or "").casefold() in str(item.get("reason_text") or "").casefold() or str(protocol.get("protocol_name") or "").casefold() in str(item.get("reason_text") or "").casefold() for item in matching_applied)
        )
        if protocol_applied:
            decision_status = "applied"
        elif blockers:
            decision_status = "blocked"
        elif timing_status == "due":
            decision_status = "review_due"
        else:
            decision_status = "forecast"
        catalog_product = product_by_id.get(str(protocol.get("product_catalog_id") or "")) or {}
        candidates.append({
            **protocol, "projection": projection, "decision_status": decision_status,
            "in_cellar": bool(catalog_product.get("in_cellar")), "stock": catalog_product.get("stock") or [],
            "timing_status": timing_status, "timing_detail": timing_detail,
            "predicted_for": predicted_for, "blockers": blockers, "advisory": advisory,
            "required_lab_analytes": required_labs, "lab_evidence_used": used_labs,
            "lab_evidence_status": (lab_evidence or {}).get("status") if lab_evidence is not None else "not_checked",
            "lab_candidates": (lab_evidence or {}).get("candidates", []) if lab_evidence is not None else [],
            "density_drop_points": density_drop_points,
            "confidence": "medium" if projection["status"] == "calculated" and not blockers else "low",
            "approval_required": True, "automatic_instruction": False,
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
            "confidence": "low", "approval_required": True, "automatic_instruction": False,
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
                "decision_status": item.get("decision_status"), "projection": item.get("projection"),
                "timing_detail": item.get("timing_detail"), "preparation": item.get("preparation"),
                "blockers": item.get("blockers") or [], "stock": item.get("stock") or [],
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
        "status": "review_due" if due else "blocked" if blocked else "monitoring",
        "due_count": due, "blocked_count": blocked, "density_drop_points": density_drop_points,
        "density_drop_rate_points_per_day": round(drop_rate, 1) if drop_rate is not None else None,
        "decisions": candidates, "batch_recipe": batch_recipe, "manufacturer_recipes": manufacturer_recipes,
        "best_fit_manufacturer": best_fit_manufacturer,
        "policy": "The batch plan groups purchased products by purpose. Choose-one alternatives and conditional products are never summed into an automatic combined recipe; the enologist selects each product, purpose, exact rate, and application.",
    }


def suggest_products(lot: dict[str, Any], products: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """Rank official products as review candidates, never as treatment instructions."""
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
        ranked.append({**product, "suggestion_score": score, "suggestion_reason": "; ".join(dict.fromkeys(reasons)), "projection": projection, "recommendation_status": "enologist_review", "is_automatic_instruction": False})
    ranked.sort(key=lambda row: (-row["suggestion_score"], str(row.get("range_name")), str(row.get("product_name"))))
    return ranked[:limit]


def refresh_enology_additive_predictions() -> dict[str, Any]:
    """Persist an auditable current prediction snapshot for every active cellar lot."""
    lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,w.volume_l,w.fruit_kg,w.initial_l,w.variety_summary,s.vintage_year,p.wine_color,p.target_style,"
        "p.yan_mg_l,p.yan_target_mg_l,p.potential_alcohol_pct,p.must_turbidity_ntu,p.fruit_condition,p.laccase_u_ml,"
        "p.anthocyanin_tannin_ratio,p.inoculated_at,p.planned_filtration_at "
        "FROM wine_lots w JOIN seasons s ON s.id=w.season_id LEFT JOIN enology_process_profiles p ON p.wine_lot_id=w.id AND p.estate_id=w.estate_id "
        "WHERE w.estate_id=%s AND w.stage NOT IN ('bottled','closed') ORDER BY w.started_at,w.code",
        (estate_id(),),
    )
    protocols, products = protocol_rows(), catalog_rows()
    saved, due, blocked = 0, 0, 0
    for lot in lots:
        readings = fetch_all(
            "SELECT observed_at,density_sg,brix,babo,temp_c,ph FROM fermentation_observations WHERE estate_id=%s AND wine_lot_id=%s ORDER BY observed_at",
            (estate_id(), lot["id"]),
        )
        additions = fetch_all(
            "SELECT additive_name,event_status,applied_at,reason_text FROM enology_addition_events WHERE estate_id=%s AND wine_lot_id=%s",
            (estate_id(), lot["id"]),
        )
        lab_evidence = lot_lab_evidence(lot, int(lot["vintage_year"]))
        decision_lot = lot_with_lab_measurements(lot, lab_evidence)
        pipeline = additive_prediction_pipeline(decision_lot, protocols, readings, additions, products=products, lab_evidence=lab_evidence)
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO enology_additive_prediction_snapshots (id,estate_id,wine_lot_id,model_version,prediction_status,due_count,blocked_count,pipeline_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_id(), estate_id(), lot["id"], ADDITIVE_PREDICTION_MODEL, pipeline["status"], pipeline["due_count"], pipeline["blocked_count"], json.dumps(json_ready(pipeline))),
            )
        saved += 1
        due += pipeline["due_count"]
        blocked += pipeline["blocked_count"]
    with transaction() as (_, cursor):
        cursor.execute("DELETE FROM enology_additive_prediction_snapshots WHERE estate_id=%s AND predicted_at<NOW()-INTERVAL 90 DAY", (estate_id(),))
    return {"status": "processed", "lots": saved, "review_due": due, "blocked": blocked, "model_version": ADDITIVE_PREDICTION_MODEL}
