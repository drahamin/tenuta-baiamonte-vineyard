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
    return fetch_all(
        "SELECT id,manufacturer,product_name,range_code,range_name,product_class,wine_colors,process_stages,description,product_url,pds_url,sds_url,dose_min,dose_max,dose_unit,dose_basis,dose_verified,source_url,source_checked_at,present_in_latest "
        "FROM enology_product_catalog WHERE active=1 AND present_in_latest=1 ORDER BY manufacturer,range_name,product_name"
    )


ADDITIVE_PREDICTION_MODEL = "enology-additive-decisions-v1"


def protocol_rows() -> list[dict[str, Any]]:
    """Return source-verified use cases rather than collapsing a product to one dose."""
    return fetch_all(
        "SELECT r.id,r.product_catalog_id,r.protocol_code,r.protocol_name,r.purpose,r.wine_colors,r.process_stages,r.trigger_code,"
        "r.dose_min,r.dose_max,r.dose_unit,r.dose_basis,r.preparation,r.application_instructions,r.prerequisites,r.incompatibilities,"
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


def additive_prediction_pipeline(
    lot: dict[str, Any], protocols: list[dict[str, Any]], readings: list[dict[str, Any]],
    additions: list[dict[str, Any]], *, products: list[dict[str, Any]] | None = None, now: datetime | None = None,
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
            blockers.append("Record the lot volume or grape weight required by this product-sheet dose.")
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
        candidates.append({
            **protocol, "projection": projection, "decision_status": decision_status,
            "timing_status": timing_status, "timing_detail": timing_detail,
            "predicted_for": predicted_for, "blockers": blockers, "advisory": advisory,
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
    return {
        "model_version": ADDITIVE_PREDICTION_MODEL, "predicted_at": now,
        "status": "review_due" if due else "blocked" if blocked else "monitoring",
        "due_count": due, "blocked_count": blocked, "density_drop_points": density_drop_points,
        "density_drop_rate_points_per_day": round(drop_rate, 1) if drop_rate is not None else None,
        "decisions": candidates,
        "policy": "Forecasts calculate source-verified ranges and timing gates only; the enologist selects the product, purpose, rate, and application.",
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
        score, reasons = 1, [f"Official LAFFORT {product.get('range_name') or product.get('product_class')} catalog entry"]
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
        "SELECT w.id,w.code,w.name,w.stage,w.volume_l,w.fruit_kg,w.initial_l,w.variety_summary,p.wine_color,p.target_style,"
        "p.yan_mg_l,p.yan_target_mg_l,p.potential_alcohol_pct,p.must_turbidity_ntu,p.fruit_condition,p.laccase_u_ml,"
        "p.anthocyanin_tannin_ratio,p.inoculated_at,p.planned_filtration_at "
        "FROM wine_lots w LEFT JOIN enology_process_profiles p ON p.wine_lot_id=w.id AND p.estate_id=w.estate_id "
        "WHERE w.estate_id=%s AND w.stage NOT IN ('bottled','closed') ORDER BY w.started_at,w.code",
        (estate_id(),),
    )
    protocols, products = protocol_rows(), catalog_rows()
    saved, due, blocked = 0, 0, 0
    for lot in lots:
        readings = fetch_all(
            "SELECT observed_at,density_sg,brix,temp_c,ph FROM fermentation_observations WHERE estate_id=%s AND wine_lot_id=%s ORDER BY observed_at",
            (estate_id(), lot["id"]),
        )
        additions = fetch_all(
            "SELECT additive_name,event_status,applied_at,reason_text FROM enology_addition_events WHERE estate_id=%s AND wine_lot_id=%s",
            (estate_id(), lot["id"]),
        )
        pipeline = additive_prediction_pipeline(lot, protocols, readings, additions, products=products)
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
