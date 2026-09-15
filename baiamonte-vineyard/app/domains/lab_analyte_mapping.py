"""Reusable AI-assisted mapping for new laboratory analyte labels and units."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import urllib.request
from typing import Any

from ..ai_usage import ai_response_options, record_ai_usage
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..enology_measurements import normalize_enology_measurement
from ..service import estate_id, new_id


def mapping_key(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    raw = "".join(character for character in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9%]+", "_", raw).strip("_")


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if isinstance(content.get("text"), str):
                return content["text"]
    return ""


def _validated_proposal(
    proposal: dict[str, Any], row: dict[str, Any], definitions: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    code = str(proposal.get("canonical_code") or "")
    if code not in definitions or float(proposal.get("confidence") or 0) < 0.9:
        return None
    try:
        multiplier = float(proposal.get("conversion_multiplier") or 1)
    except (TypeError, ValueError):
        return None
    if not 0.000001 <= multiplier <= 1000000:
        return None
    canonical_unit = str(proposal.get("canonical_unit") or definitions[code].get("default_unit") or "").strip()
    numeric = row.get("numeric_value")
    if numeric is not None:
        check = normalize_enology_measurement(code, float(numeric) * multiplier, canonical_unit)
        if not check["usable"]:
            return None
    return {
        "canonical_code": code, "canonical_name": definitions[code]["name"],
        "canonical_unit": canonical_unit, "conversion_multiplier": multiplier,
        "confidence": float(proposal["confidence"]),
    }


def map_sample_analytes(sample_id: str) -> dict[str, Any]:
    """Reuse saved mappings, then ask AI once for unresolved labels and validate its proposals."""
    from .enology_process import ENOLOGY_ANALYTES, canonical_enology_analyte

    rows = fetch_all(
        "SELECT id,analyte_code,analyte_name,numeric_value,text_value,unit,analyte_mapping_id,analyte_mapping_status FROM lab_results WHERE sample_id=%s",
        (sample_id,),
    )
    unresolved: list[dict[str, Any]] = []
    linked = 0
    for row in rows:
        canonical = canonical_enology_analyte(row.get("analyte_code"), row.get("analyte_name"), row.get("unit"))
        unit_check = normalize_enology_measurement(canonical["code"], row.get("numeric_value"), row.get("unit")) if canonical else None
        if row.get("analyte_mapping_id"):
            continue
        if canonical and (row.get("numeric_value") is None or unit_check["usable"]):
            with transaction() as (_, cursor):
                cursor.execute("UPDATE lab_results SET analyte_mapping_status='static',analyte_mapping_checked_at=NOW(6) WHERE id=%s", (row["id"],))
            continue
        keys = (mapping_key(row.get("analyte_code")), mapping_key(row.get("analyte_name")), mapping_key(row.get("unit")))
        saved = fetch_one(
            "SELECT id FROM enology_analyte_mappings WHERE estate_id=%s AND source_code_key=%s AND source_name_key=%s AND source_unit_key=%s",
            (estate_id(), *keys),
        )
        if saved:
            with transaction() as (_, cursor):
                cursor.execute("UPDATE lab_results SET analyte_mapping_id=%s,analyte_mapping_status='mapped',analyte_mapping_checked_at=NOW(6) WHERE id=%s", (saved["id"], row["id"]))
            linked += 1
        else:
            unresolved.append(row)
    if not unresolved:
        return {"status": "mapped", "linked": linked, "unresolved": 0}
    settings = get_settings()
    if not settings.openai_api_key:
        return {"status": "unmapped", "linked": linked, "unresolved": len(unresolved), "reason": "OpenAI not configured"}
    allowed = {code: {"name": item["name"], "unit": item.get("default_unit")} for code, item in ENOLOGY_ANALYTES.items()}
    prompt = (
        "Map unfamiliar wine laboratory analytes to the supplied canonical enology registry. Return JSON only with a mappings array. "
        "Each mapping must contain result_id, canonical_code or null, canonical_unit, conversion_multiplier, confidence from 0 to 1, and rationale. "
        "Use null when the name, method basis, or unit is ambiguous. Never invent a conversion; distinguish concentration bases such as acid equivalents. "
        "A high confidence mapping means the analyte identity and dimensional conversion are unambiguous. Original evidence will remain unchanged.\nRegistry:\n"
        + json.dumps(allowed, ensure_ascii=False) + "\nResults:\n" + json.dumps(unresolved, default=str, ensure_ascii=False)
    )
    body = json.dumps({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text": {"format": {"type": "json_object"}},
        **ai_response_options(),
    }).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode())
        record_ai_usage("lab_analyte_mapping", result, hashlib.sha256(sample_id.encode()).hexdigest()[:24])
        proposed = json.loads(_response_text(result) or "{}").get("mappings") or []
    except Exception as error:
        return {"status": "unmapped", "linked": linked, "unresolved": len(unresolved), "reason": str(error)[:300]}
    by_id = {str(row.get("result_id")): row for row in proposed if isinstance(row, dict)}
    accepted = 0
    with transaction() as (_, cursor):
        for row in unresolved:
            proposal = _validated_proposal(by_id.get(str(row["id"])) or {}, row, ENOLOGY_ANALYTES)
            if not proposal:
                continue
            mapping_id = new_id()
            keys = (mapping_key(row.get("analyte_code")), mapping_key(row.get("analyte_name")), mapping_key(row.get("unit")))
            cursor.execute(
                "INSERT INTO enology_analyte_mappings (id,estate_id,source_code_key,source_name_key,source_unit_key,canonical_code,canonical_name,canonical_unit,conversion_multiplier,confidence,model_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE canonical_code=VALUES(canonical_code),canonical_name=VALUES(canonical_name),canonical_unit=VALUES(canonical_unit),conversion_multiplier=VALUES(conversion_multiplier),confidence=VALUES(confidence),model_version=VALUES(model_version)",
                (mapping_id, estate_id(), *keys, proposal["canonical_code"], proposal["canonical_name"], proposal["canonical_unit"], proposal["conversion_multiplier"], proposal["confidence"], settings.openai_model),
            )
            cursor.execute(
                "SELECT id FROM enology_analyte_mappings WHERE estate_id=%s AND source_code_key=%s AND source_name_key=%s AND source_unit_key=%s",
                (estate_id(), *keys),
            )
            saved = cursor.fetchone()
            if saved:
                cursor.execute("UPDATE lab_results SET analyte_mapping_id=%s,analyte_mapping_status='mapped',analyte_mapping_checked_at=NOW(6) WHERE id=%s", (saved["id"], row["id"]))
                accepted += 1
        for row in unresolved:
            cursor.execute(
                "UPDATE lab_results SET analyte_mapping_status=IF(analyte_mapping_id IS NULL,'ambiguous','mapped'),analyte_mapping_checked_at=NOW(6) WHERE id=%s",
                (row["id"],),
            )
    return {"status": "mapped" if accepted else "unmapped", "linked": linked, "accepted": accepted, "unresolved": len(unresolved) - accepted}


def refresh_unmapped_lab_analytes(limit: int = 25) -> dict[str, Any]:
    """Retry new mappings and revisit ambiguous results on a slow cadence."""
    samples = fetch_all(
        "SELECT sample_id,MIN(COALESCE(analyte_mapping_checked_at,'1900-01-01')) oldest_check FROM lab_results "
        "WHERE analyte_mapping_status='pending' OR (analyte_mapping_status='ambiguous' AND analyte_mapping_checked_at<DATE_SUB(NOW(),INTERVAL 7 DAY)) "
        "GROUP BY sample_id ORDER BY oldest_check LIMIT %s",
        (max(1, min(int(limit), 100)),),
    )
    outcomes = [map_sample_analytes(str(row["sample_id"])) for row in samples]
    return {"samples": len(samples), "mapped": sum(int(row.get("accepted") or 0) + int(row.get("linked") or 0) for row in outcomes)}
