"""Official LAFFORT product catalog and guarded enology suggestions."""

from __future__ import annotations

from datetime import datetime
from html import unescape
import json
import re
import unicodedata
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from ..db import fetch_all, transaction
from ..service import json_ready, new_id


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
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", value).casefold().split())


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
