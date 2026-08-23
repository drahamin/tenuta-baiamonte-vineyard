"""Italian Ministry product catalog and Baiamonte regulatory overlays.

The national register establishes product identity and administrative status.
It does not establish a crop, target, dose, PHI, REI, or tank-mix direction;
those fields enter the treatment engine only through a separately reviewed
current label and Agronomist approval.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import re
import subprocess
import unicodedata
import urllib.request
from typing import Any, Callable

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, new_id


CATALOG_LANDING_URL = "https://www.dati.salute.gov.it/it/dataset/fitosanitari/"
CATALOG_FALLBACK_URL = "https://www.dati.salute.gov.it/sites/default/files/opendata/PROD_FTS_6_20260817.json"
CATALOG_SOURCE_REFERENCE = "https://www.salute.gov.it/new/it/banche-dati/banca-dati-dei-prodotti-fitosanitari/"
MAX_CATALOG_BYTES = 40 * 1024 * 1024
CATALOG_WRITE_BATCH = 50


def normalize_registration(value: Any) -> str:
    text = re.sub(r"[^0-9A-Z]", "", str(value or "").strip().upper())
    return text.zfill(6) if text.isdigit() and len(text) < 6 else text[:100]


def normalize_product_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").upper())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()[:255]


def _date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            pass
    return None


def _yes(value: Any) -> int:
    return int(str(value or "").strip().casefold() in {"si", "sì", "yes", "true", "1"})


def administrative_status(value: Any, expires_on: date | None = None) -> str:
    text = str(value or "").strip().casefold()
    if "revoc" in text:
        return "revoked"
    if "sosp" in text:
        return "suspended"
    if "scad" in text:
        return "expired"
    if expires_on and expires_on < date.today():
        return "expired"
    if "autoriz" in text or "valid" in text:
        return "authorized"
    return "unknown"


def formulation_profile(code: Any, description: Any) -> tuple[str, str]:
    normalized = str(code or "").strip().upper()
    text = f"{normalized} {description or ''}".casefold()
    if normalized in {"WG", "WDG"} or "granul" in text:
        return "water_dispersible_granule", "kg"
    if normalized in {"WP", "SP", "DP"} or "polvere" in text:
        return "water_soluble_powder" if normalized == "SP" else "wettable_powder", "kg"
    if normalized in {"SC", "SL", "EC", "EW", "SE", "OD", "CS"} or "liquid" in text or "sospensione" in text:
        return "liquid", "L"
    if "gel" in text:
        return "gel", "L"
    return "unknown", "kg"


def _read_url(url: str, *, timeout: int = 90) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Tenuta-Baiamonte-Regulatory-Sync/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_CATALOG_BYTES + 1)
    except Exception as urllib_error:
        # The Ministry endpoint currently rejects TLS negotiation from some
        # Python/OpenSSL builds while accepting the system TLS client. Keep a
        # bounded, argument-list-only fallback for those installations.
        try:
            result = subprocess.run(
                ["curl", "--location", "--fail", "--silent", "--show-error", "--max-time", str(timeout),
                 "--max-filesize", str(MAX_CATALOG_BYTES), "--user-agent", "Tenuta-Baiamonte-Regulatory-Sync/1.0", url],
                check=True, capture_output=True, timeout=timeout + 5,
            )
            payload = result.stdout
        except (OSError, subprocess.SubprocessError) as curl_error:
            raise RuntimeError(f"Official Ministry catalog could not be downloaded: {urllib_error}") from curl_error
    if len(payload) > MAX_CATALOG_BYTES:
        raise ValueError("Ministry product catalog exceeds the configured 40 MB safety limit")
    return payload


def discover_catalog_url(reader: Callable[[str], bytes] = _read_url) -> str:
    try:
        html = reader(CATALOG_LANDING_URL).decode("utf-8", errors="replace")
        matches = re.findall(r'https?://[^"\'<>\s]+/PROD_FTS_6_(\d{8})\.json', html, re.I)
        if matches:
            version = max(matches)
            return re.search(rf'https?://[^"\'<>\s]+/PROD_FTS_6_{version}\.json', html, re.I).group(0)
        relative = re.findall(r'[/A-Za-z0-9_.:-]*PROD_FTS_6_(\d{8})\.json', html, re.I)
        if relative:
            version = max(relative)
            return f"https://www.dati.salute.gov.it/sites/default/files/opendata/PROD_FTS_6_{version}.json"
    except Exception:
        pass
    return CATALOG_FALLBACK_URL


def parse_catalog(payload: bytes) -> list[dict[str, Any]]:
    decoded = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(decoded, list):
        raise ValueError("Ministry product catalog is not a JSON list")
    rows: list[dict[str, Any]] = []
    for raw in decoded:
        if not isinstance(raw, dict):
            continue
        registration = normalize_registration(raw.get("num_registrazione"))
        name = str(raw.get("denominazione_prodotto") or "").strip()
        if not registration or not name:
            continue
        expires = _date(raw.get("data_scadenza_autorizzazione"))
        rows.append({
            "registration_number": registration,
            "product_name": name[:255],
            "normalized_name": normalize_product_name(name),
            "authorization_holder": str(raw.get("ragione_sociale") or "").strip()[:255] or None,
            "registered_on": _date(raw.get("data_registrazione")),
            "authorization_expires_on": expires,
            "administrative_status": administrative_status(raw.get("stato_amministrativo"), expires),
            "hazard_statements": str(raw.get("indicazioni_di_pericolo") or "").strip() or None,
            "activity": str(raw.get("attivita") or "").strip() or None,
            "formulation_code": str(raw.get("codice_formulazione") or "").strip()[:80] or None,
            "formulation_description": str(raw.get("descrizione_formulazione") or "").strip()[:255] or None,
            "active_substances": str(raw.get("sostanze_attive") or "").strip() or None,
            "active_content": str(raw.get("contenuto_per_100g_di_prodotto") or "").strip() or None,
            "parallel_import": _yes(raw.get("importazione_parallela")),
            "ornamental_only": int(_yes(raw.get("PFnPO")) or _yes(raw.get("PFnPE"))),
            "revoked_on": _date(raw.get("data_decorrenza_revoca")),
            "revocation_reason": str(raw.get("motivo_della revoca") or "").strip() or None,
            "raw_json": json.dumps(raw, ensure_ascii=False),
        })
    if len(rows) < 100:
        raise ValueError("Ministry product catalog contains too few usable records")
    return rows


def _version_date(source_url: str) -> date | None:
    match = re.search(r"_(\d{8})\.json", source_url)
    return datetime.strptime(match.group(1), "%Y%m%d").date() if match else None


def _overlay_current_products(cursor: Any, rows: list[dict[str, Any]], source_url: str, version: date | None) -> dict[str, int]:
    by_registration = {row["registration_number"]: row for row in rows}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_name.setdefault(row["normalized_name"], []).append(row)
    cursor.execute("SELECT id,name,registration_number,active_ingredient FROM products WHERE estate_id=%s AND active=1 AND product_type='plant_protection'", (estate_id(),))
    products = list(cursor.fetchall())
    matched = exact = review = 0
    for product in products:
        registration = normalize_registration(product.get("registration_number"))
        official = by_registration.get(registration) if registration else None
        method, confidence, review_status = "exact_registration", 1.0, "automatic_exact"
        if not official:
            name_matches = by_name.get(normalize_product_name(product.get("name"))) or []
            if len(name_matches) != 1:
                continue
            official = name_matches[0]
            method, confidence, review_status = "normalized_name", 0.82, "needs_review"
        matched += 1
        exact += int(method == "exact_registration")
        review += int(method != "exact_registration")
        cursor.execute(
            "INSERT INTO treatment_product_regulatory_overlays (id,estate_id,product_id,registration_number,match_method,match_confidence,review_status,source_version_date,synced_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(6)) ON DUPLICATE KEY UPDATE registration_number=VALUES(registration_number),"
            "match_method=VALUES(match_method),match_confidence=VALUES(match_confidence),review_status=IF(review_status IN ('approved','rejected'),review_status,VALUES(review_status)),"
            "source_version_date=VALUES(source_version_date),synced_at=NOW(6)",
            (new_id(), estate_id(), product["id"], official["registration_number"], method, confidence, review_status, version),
        )
        evidence_status = "verified" if method == "exact_registration" else "needs_review"
        cursor.execute(
            "INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,notes) "
            "VALUES (%s,%s,%s,'official_register',%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),"
            "evidence_date=VALUES(evidence_date),verification_status=VALUES(verification_status),notes=VALUES(notes)",
            (new_id(), estate_id(), product["id"], f"italian-ministry:{official['registration_number']}", source_url, version,
             evidence_status, f"Italian Ministry overlay · {official['administrative_status']} · {official['product_name']} · identity match {method}. Crop, target and rate still require the current authorized label."),
        )
        if method == "exact_registration":
            cursor.execute(
                "UPDATE products SET active_ingredient=COALESCE(NULLIF(active_ingredient,''),%s) WHERE id=%s AND estate_id=%s",
                (str(official.get("active_substances") or "")[:255] or None, product["id"], estate_id()),
            )
    return {"matched_products": matched, "exact_matches": exact, "review_matches": review}


def sync_ministry_product_catalog(*, reader: Callable[[str], bytes] = _read_url, source_url: str | None = None) -> dict[str, Any]:
    url = source_url or discover_catalog_url(reader)
    version = _version_date(url)
    run_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO ministry_product_catalog_sync_runs (id,status,source_url,source_version_date) VALUES (%s,'running',%s,%s)",
            (run_id, url, version),
        )
    try:
        rows = parse_catalog(reader(url))
        values = [(
            row["registration_number"], row["product_name"], row["normalized_name"], row["authorization_holder"], row["registered_on"],
            row["authorization_expires_on"], row["administrative_status"], row["hazard_statements"], row["activity"], row["formulation_code"],
            row["formulation_description"], row["active_substances"], row["active_content"], row["parallel_import"], row["ornamental_only"],
            row["revoked_on"], row["revocation_reason"], url, version, row["raw_json"],
        ) for row in rows]
        with transaction() as (_, cursor):
            cursor.execute("UPDATE ministry_product_catalog SET present_in_latest=0")
            sql = (
                "INSERT INTO ministry_product_catalog (registration_number,product_name,normalized_name,authorization_holder,registered_on,authorization_expires_on,"
                "administrative_status,hazard_statements,activity,formulation_code,formulation_description,active_substances,active_content,parallel_import,ornamental_only,"
                "revoked_on,revocation_reason,source_url,source_version_date,raw_json,present_in_latest,synced_at) VALUES ("
                + ",".join(["%s"] * 20) + ",1,NOW(6)) ON DUPLICATE KEY UPDATE product_name=VALUES(product_name),normalized_name=VALUES(normalized_name),"
                "authorization_holder=VALUES(authorization_holder),registered_on=VALUES(registered_on),authorization_expires_on=VALUES(authorization_expires_on),"
                "administrative_status=VALUES(administrative_status),hazard_statements=VALUES(hazard_statements),activity=VALUES(activity),formulation_code=VALUES(formulation_code),"
                "formulation_description=VALUES(formulation_description),active_substances=VALUES(active_substances),active_content=VALUES(active_content),"
                "parallel_import=VALUES(parallel_import),ornamental_only=VALUES(ornamental_only),revoked_on=VALUES(revoked_on),revocation_reason=VALUES(revocation_reason),"
                "source_url=VALUES(source_url),source_version_date=VALUES(source_version_date),raw_json=VALUES(raw_json),present_in_latest=1,synced_at=NOW(6)"
            )
            # Raw official rows are retained for audit and can make one large
            # multi-row upsert exceed MariaDB's per-query read timeout on the
            # Home Assistant add-on network. Small bounded statements keep the
            # import transactional without weakening the connection timeout.
            for start in range(0, len(values), CATALOG_WRITE_BATCH):
                cursor.executemany(sql, values[start:start + CATALOG_WRITE_BATCH])
            cursor.execute(
                "INSERT INTO treatment_regulatory_sources (id,source_code,authority,source_scope,version_date,source_url,refresh_frequency,checked_on,notes) "
                "VALUES (%s,'italian_ministry_product_catalog','Ministero della Salute','National plant-protection product identity and administrative status',%s,%s,'weekly',CURDATE(),%s) "
                "ON DUPLICATE KEY UPDATE authority=VALUES(authority),source_scope=VALUES(source_scope),version_date=VALUES(version_date),source_url=VALUES(source_url),refresh_frequency=VALUES(refresh_frequency),checked_on=CURDATE(),notes=VALUES(notes)",
                (new_id(), version, url, "Not a crop/use label source. Baiamonte crop, target, rate, PHI, REI and mixture decisions remain separately reviewed."),
            )
            overlay = _overlay_current_products(cursor, rows, url, version)
            cursor.execute(
                "UPDATE ministry_product_catalog_sync_runs SET status='processed',source_rows=%s,imported_rows=%s,matched_products=%s,exact_matches=%s,review_matches=%s,completed_at=NOW(6) WHERE id=%s",
                (len(rows), len(values), overlay["matched_products"], overlay["exact_matches"], overlay["review_matches"], run_id),
            )
        return {"status": "processed", "run_id": run_id, "source_url": url, "source_version_date": version, "source_rows": len(rows), **overlay}
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute(
                "UPDATE ministry_product_catalog_sync_runs SET status='failed',error_text=%s,completed_at=NOW(6) WHERE id=%s",
                (str(error)[:4000], run_id),
            )
        raise


def catalog_status() -> dict[str, Any]:
    latest = fetch_one("SELECT * FROM ministry_product_catalog_sync_runs ORDER BY started_at DESC LIMIT 1") or {}
    counts = fetch_one(
        "SELECT COUNT(*) total,COALESCE(SUM(administrative_status='authorized' AND present_in_latest=1),0) authorized,COALESCE(SUM(administrative_status IN ('revoked','suspended','expired')),0) blocked FROM ministry_product_catalog"
    ) or {}
    overlays = fetch_all(
        "SELECT p.id product_id,p.name local_product,p.registration_number local_registration,o.match_method,o.match_confidence,o.review_status,"
        "c.registration_number ministry_registration,c.product_name ministry_product,c.administrative_status,c.authorization_expires_on,c.active_substances,c.formulation_code,c.source_version_date "
        "FROM products p LEFT JOIN treatment_product_regulatory_overlays o ON o.product_id=p.id AND o.estate_id=p.estate_id "
        "LEFT JOIN ministry_product_catalog c ON c.registration_number=o.registration_number "
        "WHERE p.estate_id=%s AND p.active=1 AND p.product_type='plant_protection' ORDER BY p.name",
        (estate_id(),),
    )
    return {"latest_sync": latest, "counts": counts, "overlays": overlays, "source": {"landing_url": CATALOG_LANDING_URL, "register_url": CATALOG_SOURCE_REFERENCE}}


def search_catalog(query: str, *, status: str = "authorized", limit: int = 30) -> list[dict[str, Any]]:
    query = str(query or "").strip()
    if len(query) < 2:
        return []
    limit = min(100, max(1, int(limit)))
    normalized = normalize_product_name(query)
    status_clause = "AND administrative_status=%s" if status in {"authorized", "suspended", "revoked", "expired", "unknown"} else ""
    params: list[Any] = [f"%{normalized}%", f"%{query}%", f"%{query}%"]
    if status_clause:
        params.append(status)
    params.append(limit)
    sql = (
        "SELECT registration_number,product_name,authorization_holder,authorization_expires_on,administrative_status,activity,formulation_code,formulation_description,"
        "active_substances,active_content,hazard_statements,parallel_import,ornamental_only,source_url,source_version_date "
        "FROM ministry_product_catalog WHERE present_in_latest=1 AND (normalized_name LIKE %s OR registration_number LIKE %s OR active_substances LIKE %s) "
        + status_clause + " ORDER BY (normalized_name=%s) DESC,product_name LIMIT %s"
    )
    params.insert(-1, normalized)
    return fetch_all(sql, tuple(params))


def adopt_catalog_product(registration_number: str, *, actor: str) -> dict[str, Any]:
    registration = normalize_registration(registration_number)
    official = fetch_one("SELECT * FROM ministry_product_catalog WHERE registration_number=%s AND present_in_latest=1", (registration,))
    if not official:
        raise ValueError("Choose a product from the current Ministry catalog")
    existing = fetch_one("SELECT id,name FROM products WHERE estate_id=%s AND registration_number=%s", (estate_id(), registration))
    if existing:
        return {"created": False, "product_id": existing["id"], "product_name": existing["name"], "status": "already_in_catalog"}
    duplicate = fetch_one("SELECT id,name FROM products WHERE estate_id=%s AND LOWER(name)=LOWER(%s)", (estate_id(), official["product_name"]))
    if duplicate:
        raise ValueError("A Baiamonte product with this name already exists; review its Ministry overlay instead")
    product_id = new_id()
    form, unit = formulation_profile(official.get("formulation_code"), official.get("formulation_description"))
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO products (id,estate_id,name,product_type,active_ingredient,registration_number,unit,supplier,notes,active) VALUES (%s,%s,%s,'plant_protection',%s,%s,%s,%s,%s,1)",
            (product_id, estate_id(), official["product_name"], str(official.get("active_substances") or "")[:255] or None, registration, unit,
             str(official.get("authorization_holder") or "")[:180] or None, "Imported from the Italian Ministry product register for label review. National registration does not establish a vineyard crop, target, rate, PHI, REI, or tank-mix direction."),
        )
        cursor.execute(
            "INSERT INTO treatment_product_profiles (id,estate_id,product_id,concentrate_form,formulation_code,measure_unit,verification_status,estate_authorization_status,eligible_for_projection,source_summary,active) "
            "VALUES (%s,%s,%s,%s,%s,%s,'needs_container_label','not_confirmed',0,%s,1)",
            (new_id(), estate_id(), product_id, form, official.get("formulation_code"), unit,
             "Official Ministry identity and administrative status imported. Current full label and Agronomist crop/use approval remain required."),
        )
        cursor.execute(
            "INSERT INTO treatment_product_regulatory_overlays (id,estate_id,product_id,registration_number,match_method,match_confidence,review_status,reviewed_by,reviewed_at,source_version_date,synced_at) "
            "VALUES (%s,%s,%s,%s,'exact_registration',1,'automatic_exact',%s,NOW(6),%s,NOW(6))",
            (new_id(), estate_id(), product_id, registration, actor, official.get("source_version_date")),
        )
        cursor.execute(
            "INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,notes) "
            "VALUES (%s,%s,%s,'official_register',%s,%s,%s,'verified',%s)",
            (new_id(), estate_id(), product_id, f"italian-ministry:{registration}", official.get("source_url"), official.get("source_version_date"),
             "Official product identity and administrative status only; full authorized use label is still required."),
        )
        audit(cursor, "adopt_reference", "treatment_product", product_id, {"registration_number": registration, "product_name": official["product_name"], "administrative_status": official["administrative_status"], "eligible_for_projection": False}, actor)
    return {"created": True, "product_id": product_id, "product_name": official["product_name"], "status": "label_review_required", "eligible_for_projection": False}


def approve_catalog_product_use(product_id: str, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
    product = fetch_one(
        "SELECT p.*,o.registration_number overlay_registration,o.review_status overlay_review,c.administrative_status ministry_status,c.authorization_expires_on ministry_expires_on "
        "FROM products p JOIN treatment_product_regulatory_overlays o ON o.product_id=p.id AND o.estate_id=p.estate_id "
        "JOIN ministry_product_catalog c ON c.registration_number=o.registration_number WHERE p.id=%s AND p.estate_id=%s AND p.active=1",
        (product_id, estate_id()),
    )
    if not product:
        raise ValueError("Product does not have a current Ministry overlay")
    if product.get("ministry_status") != "authorized":
        raise ValueError(f"Ministry administrative status is {product.get('ministry_status') or 'unknown'}; projection remains blocked")
    expires = product.get("ministry_expires_on")
    if expires and expires < date.today():
        raise ValueError("Ministry authorization date has expired; projection remains blocked")
    required_checks = ("current_label_confirmed", "italy_authorization_confirmed", "crop_target_confirmed", "dose_limits_confirmed", "phi_rei_confirmed")
    if not all(bool(payload.get(name)) for name in required_checks):
        raise ValueError("Confirm the current label, Italian authorization, crop/target, dose limits, and PHI/REI")
    crop_scope = str(payload.get("crop_scope") or "vineyard").strip().casefold()
    if crop_scope not in {"vineyard", "olives"}:
        raise ValueError("Choose vineyard or olives")
    target_code = re.sub(r"[^a-z0-9_]+", "_", str(payload.get("target_code") or "").strip().casefold()).strip("_")[:100]
    target_name = str(payload.get("target_name") or target_code.replace("_", " ")).strip()[:180]
    dose_unit = str(payload.get("dose_unit") or "").strip()[:40]
    if not target_code or dose_unit not in {"kg/ha", "L/ha", "g/100 L", "ml/100 L", "g/L"}:
        raise ValueError("Record a target and a supported label dose unit")
    try:
        minimum = float(payload.get("min_dose"))
        maximum = float(payload.get("max_dose") if payload.get("max_dose") not in (None, "") else minimum)
    except (TypeError, ValueError) as error:
        raise ValueError("Record numeric minimum and maximum label doses") from error
    if minimum <= 0 or maximum < minimum:
        raise ValueError("Label dose limits are invalid")
    label_url = str(payload.get("label_url") or "").strip()
    if not label_url.startswith("https://"):
        raise ValueError("Record the current authorized label HTTPS source")
    phi_days = int(payload.get("phi_days") or 0)
    rei_hours = int(payload.get("rei_hours") or 0)
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE treatment_product_profiles SET verification_status='verified',estate_authorization_status='confirmed',estate_authorization_confirmed_on=CURDATE(),"
            "label_verified_on=CURDATE(),label_url=%s,eligible_for_projection=1,authorization_notes=%s,source_summary=%s WHERE estate_id=%s AND product_id=%s AND active=1",
            (label_url, str(payload.get("authorization_notes") or "").strip() or None,
             "Current Italian label crop/use, dose, PHI and REI were approved by the Agronomist after Ministry identity/status overlay.", estate_id(), product_id),
        )
        cursor.execute(
            "INSERT INTO product_authorized_uses (id,estate_id,product_id,crop_scope,target_code,target_name,authorization_status,authorization_expires_on,label_verified_on,label_url,min_dose,max_dose,dose_unit,phi_days,rei_hours,max_applications,minimum_interval_days,resistance_group,growth_stage_limits,environmental_restrictions,notes,active) "
            "VALUES (%s,%s,%s,%s,%s,%s,'authorized',%s,CURDATE(),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) ON DUPLICATE KEY UPDATE target_name=VALUES(target_name),authorization_status='authorized',"
            "authorization_expires_on=VALUES(authorization_expires_on),label_verified_on=CURDATE(),label_url=VALUES(label_url),min_dose=VALUES(min_dose),max_dose=VALUES(max_dose),dose_unit=VALUES(dose_unit),"
            "phi_days=VALUES(phi_days),rei_hours=VALUES(rei_hours),max_applications=VALUES(max_applications),minimum_interval_days=VALUES(minimum_interval_days),resistance_group=VALUES(resistance_group),"
            "growth_stage_limits=VALUES(growth_stage_limits),environmental_restrictions=VALUES(environmental_restrictions),notes=VALUES(notes),active=1",
            (new_id(), estate_id(), product_id, crop_scope, target_code, target_name, product.get("ministry_expires_on"), label_url, minimum, maximum, dose_unit,
             phi_days, rei_hours, int(payload.get("max_applications") or 0) or None, int(payload.get("minimum_interval_days") or 0) or None,
             str(payload.get("resistance_group") or "").strip()[:80] or None, str(payload.get("growth_stage_limits") or "").strip()[:255] or None,
             str(payload.get("environmental_restrictions") or "").strip() or None, str(payload.get("notes") or "").strip() or None),
        )
        cursor.execute(
            "INSERT INTO treatment_product_options (id,estate_id,product_id,crop_scope,target_code,mixture_role,default_decision,selection_conditions,compatibility_status,compatibility_conditions,active) "
            "VALUES (%s,%s,%s,%s,%s,'primary','candidate',%s,'not_verified',%s,1) ON DUPLICATE KEY UPDATE default_decision='candidate',selection_conditions=VALUES(selection_conditions),compatibility_status='not_verified',compatibility_conditions=VALUES(compatibility_conditions),active=1",
            (new_id(), estate_id(), product_id, crop_scope, target_code,
             "New-to-Baiamonte candidate: current disease need, label limits, weather, resistance rotation, inventory and Agronomist approval must all pass.",
             "Exact tank-mix compatibility is not established by catalog or label identity; review every proposed combination."),
        )
        cursor.execute(
            "UPDATE treatment_product_regulatory_overlays SET review_status='approved',reviewed_by=%s,reviewed_at=NOW(6),review_notes=%s WHERE estate_id=%s AND product_id=%s",
            (actor, "Agronomist approved current crop-and-target label use; historical Baiamonte outcome evidence is not yet available.", estate_id(), product_id),
        )
        cursor.execute(
            "INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,evidence_date,verification_status,observed_rate,observed_rate_max,observed_rate_unit,notes) "
            "VALUES (%s,%s,%s,'agronomist_review',%s,%s,CURDATE(),'verified',%s,%s,%s,%s) ON DUPLICATE KEY UPDATE source_reference=VALUES(source_reference),evidence_date=CURDATE(),verification_status='verified',observed_rate=VALUES(observed_rate),observed_rate_max=VALUES(observed_rate_max),observed_rate_unit=VALUES(observed_rate_unit),notes=VALUES(notes)",
            (new_id(), estate_id(), product_id, f"catalog-use:{crop_scope}:{target_code}", label_url, minimum, maximum, dose_unit,
             "First-use candidate outside Baiamonte history. Current label and Agronomist approval recorded; outcome confidence remains low until paired scouting is available."),
        )
        audit(cursor, "approve_catalog_use", "treatment_product", product_id, {"crop_scope": crop_scope, "target_code": target_code, "min_dose": minimum, "max_dose": maximum, "dose_unit": dose_unit, "phi_days": phi_days, "rei_hours": rei_hours, "new_to_baiamonte": True}, actor)
    return {"saved": True, "product_id": product_id, "product_name": product["name"], "crop_scope": crop_scope, "target_code": target_code, "eligible_for_projection": True, "confidence": "new_product_review_required"}


def review_overlay(product_id: str, *, approved: bool, actor: str, notes: str = "") -> dict[str, Any]:
    row = fetch_one(
        "SELECT o.id,o.registration_number,c.product_name,c.active_substances FROM treatment_product_regulatory_overlays o JOIN ministry_product_catalog c ON c.registration_number=o.registration_number WHERE o.estate_id=%s AND o.product_id=%s",
        (estate_id(), product_id),
    )
    if not row:
        raise ValueError("Regulatory overlay was not found")
    status = "approved" if approved else "rejected"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE treatment_product_regulatory_overlays SET review_status=%s,reviewed_by=%s,reviewed_at=NOW(6),review_notes=%s WHERE estate_id=%s AND product_id=%s",
            (status, actor, notes or None, estate_id(), product_id),
        )
        if approved:
            cursor.execute(
                "UPDATE products SET registration_number=%s,active_ingredient=COALESCE(NULLIF(active_ingredient,''),%s) WHERE estate_id=%s AND id=%s",
                (row["registration_number"], str(row.get("active_substances") or "")[:255] or None, estate_id(), product_id),
            )
        audit(cursor, "review_regulatory_overlay", "treatment_product", product_id, {"status": status, "registration_number": row["registration_number"], "notes": notes}, actor)
    return {"saved": True, "product_id": product_id, "review_status": status}


def ministry_overlay_allows_projection(row: dict[str, Any], *, reference_day: date | None = None) -> bool:
    status = row.get("ministry_status")
    if not status:
        return True
    trusted = row.get("ministry_match_method") == "exact_registration" or row.get("ministry_review_status") == "approved"
    if not trusted:
        return True
    if row.get("ministry_present") in {0, False}:
        return False
    expires = row.get("ministry_expires_on")
    return status == "authorized" and (not expires or expires >= (reference_day or date.today()))
