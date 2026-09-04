"""Canonical, source-backed estate facts shared by every application pipeline.

Official PDFs remain the immutable evidence.  This module applies status and
effective-year rules once so dashboards, models and calculations cannot select
an incomplete reference extract as an authoritative value.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .db import fetch_all, fetch_one
from .service import estate_id


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row.get("id"),
        "title": row.get("title"),
        "document_type": row.get("document_type"),
        "issuing_authority": row.get("issuing_authority"),
        "reference_number": row.get("reference_number"),
        "issue_date": row.get("issue_date"),
        "effective_year": row.get("effective_year"),
        "status": row.get("status"),
        "view_url": f"api/v1/admin/official-documents/{row.get('id')}/file",
    }


def _sum(facts: dict[str, Any], keys: tuple[str, ...]) -> float:
    return round(sum(_number(facts.get(key)) or 0 for key in keys), 4)


def authoritative_estate_facts(year: int | None = None) -> dict[str, Any]:
    """Return canonical facts, references and reconciliation at a stable grain."""
    selected_year = int(year or date.today().year)
    rows = fetch_all(
        "SELECT id,document_type,title,issuing_authority,reference_number,issue_date,effective_year,status,summary,verified_facts,related_scope "
        "FROM official_documents WHERE estate_id=%s AND status<>'draft' "
        "ORDER BY FIELD(status,'current','reference','historical','superseded'),COALESCE(issue_date,'0001-01-01') DESC,id",
        (estate_id(),),
    )
    prepared = [{**row, "verified_facts": _json(row.get("verified_facts"), {}), "related_scope": _json(row.get("related_scope"), {})} for row in rows]
    current = [row for row in prepared if row.get("status") == "current"]
    references = [row for row in prepared if row.get("status") == "reference"]

    vineyard_document = next((row for row in current if row.get("document_type") == "vineyard_register" and row["verified_facts"].get("official_vineyard_area_m2") is not None), {})
    vineyard = vineyard_document.get("verified_facts") or {}
    new_system_document = next((row for row in references if row.get("document_type") == "vineyard_register" and row["verified_facts"].get("reported_vineyard_area_m2") is not None), {})
    new_system = new_system_document.get("verified_facts") or {}
    cadastral_document = next((row for row in current if row.get("document_type") == "cadastral_record"), {})
    cadastral = cadastral_document.get("verified_facts") or {}
    deed_document = next((row for row in current if row.get("document_type") == "company_formation"), {})
    company_document = next((row for row in current if row.get("document_type") == "company_register"), {})

    pending_row = fetch_one(
        "SELECT source_date,confidence,notes,metadata FROM evidence_references WHERE estate_id=%s AND id='evidence-new-vines-registration'",
        (estate_id(),),
    ) or {}
    pending = _json(pending_row.get("metadata"), {})

    official_m2 = _number(vineyard.get("official_vineyard_area_m2"))
    pending_ha = _number(pending.get("pending_new_planting_area_ha"))
    working_ha = _number(pending.get("working_total_planted_area_ha"))
    productive_year = int(_number(pending.get("expected_productive_year")) or 0) or None
    current_productive_ha = _number(pending.get("current_production_area_ha")) or (official_m2 / 10000 if official_m2 is not None else None)
    projected_productive_ha = _number(pending.get("projected_productive_area_ha_2027")) or working_ha
    productive_ha_for_year = projected_productive_ha if productive_year and selected_year >= productive_year else current_productive_ha

    harvest_declarations: dict[str, Any] = {}
    for row in current:
        if row.get("document_type") != "harvest_declaration" or row.get("effective_year") is None:
            continue
        harvest_declarations[str(row["effective_year"])] = {
            **row["verified_facts"], "source": _source(row), "authority": "official_declaration",
        }

    parcel_keys = ("parcel_83_76_m2", "parcel_83_77_m2", "parcel_83_93_m2")
    variety_keys = ("alicante_m2", "grecanico_m2", "nerello_mascalese_m2")
    parcel_sum = _sum(vineyard, parcel_keys)
    variety_sum = _sum(vineyard, variety_keys)
    database_parcels = fetch_one(
        "SELECT COALESCE(SUM(official_vineyard_area_ha),0) official_vineyard_area_ha FROM cadastral_parcels WHERE estate_id=%s",
        (estate_id(),),
    ) or {}
    operational_blocks = fetch_one(
        "SELECT COALESCE(SUM(area_ha),0) operational_block_area_ha FROM vineyard_blocks WHERE estate_id=%s AND active=1",
        (estate_id(),),
    ) or {}
    db_official_ha = _number(database_parcels.get("official_vineyard_area_ha"))
    block_area_ha = _number(operational_blocks.get("operational_block_area_ha"))
    expected_ha = official_m2 / 10000 if official_m2 is not None else None
    checks = {
        "authoritative_register_present": bool(vineyard_document),
        "parcel_breakdown_matches_register": official_m2 is not None and abs(parcel_sum - official_m2) < 0.5,
        "variety_breakdown_matches_register": official_m2 is not None and abs(variety_sum - official_m2) < 0.5,
        "atlas_parcels_match_register": expected_ha is not None and db_official_ha is not None and abs(db_official_ha - expected_ha) < 0.00005,
        "new_system_extract_is_reference_only": bool(new_system_document) and new_system_document.get("status") == "reference",
    }
    warnings: list[str] = []
    if block_area_ha is not None and working_ha is not None and abs(block_area_ha - working_ha) >= 0.0005:
        warnings.append("Operational block areas do not yet reconcile to the approximately 1.2144 ha planted footprint; canonical whole-estate calculations use the source-backed area appropriate to their purpose.")
    if not all(checks.values()):
        warnings.append("One or more official-record consistency checks need administrative review.")

    return {
        "as_of_year": selected_year,
        "authority_policy": "Only current verified official documents populate canonical facts. Reference extracts remain visible for reconciliation and never overwrite current facts.",
        "vineyard": {
            "official_current_area_m2": official_m2,
            "official_current_area_ha": expected_ha,
            "official_current_ha": expected_ha,
            "current_productive_area_ha": current_productive_ha,
            "current_production_ha": current_productive_ha,
            "working_planted_area_ha": working_ha,
            "working_planted_ha": working_ha,
            "pending_new_planting_area_ha": pending_ha,
            "pending_new_planting_ha": pending_ha,
            "pending_area_is_approximate": bool(pending.get("area_is_approximate", True)),
            "new_planting_expected_productive_year": productive_year,
            "productive_area_ha_for_selected_year": productive_ha_for_year,
            "projected_productive_ha_by_year": {"2026": current_productive_ha, "2027": projected_productive_ha},
            "treatment_footprint_ha": working_ha,
            "basis": "The complete current register is authoritative. Any incomplete newer-system extract remains reference-only; pending planting is shown separately until official documentation is updated.",
            "variety_area_m2": {"Alicante": _number(vineyard.get("alicante_m2")), "Grecanico": _number(vineyard.get("grecanico_m2")), "Nerello Mascalese": _number(vineyard.get("nerello_mascalese_m2"))},
            "parcel_vineyard_area_m2": {"83/76": _number(vineyard.get("parcel_83_76_m2")), "83/77": _number(vineyard.get("parcel_83_77_m2")), "83/93": _number(vineyard.get("parcel_83_93_m2"))},
            "source": _source(vineyard_document) if vineyard_document else None,
            "pending_source": {"evidence_id": "evidence-new-vines-registration", "source_date": pending_row.get("source_date"), "confidence": pending_row.get("confidence"), "notes": pending_row.get("notes")},
        },
        "reference_extracts": {
            "italy_new_system_vineyard_area_m2": _number(new_system.get("reported_vineyard_area_m2")),
            "coverage_status": new_system.get("coverage_status"),
            "reconciliation_status": new_system.get("reconciliation_status"),
            "shortfall_vs_authoritative_m2": round((official_m2 or 0) - (_number(new_system.get("reported_vineyard_area_m2")) or 0), 2) if official_m2 is not None else None,
            "source": _source(new_system_document) if new_system_document else None,
        },
        "cadastral": {**cadastral, "source": _source(cadastral_document) if cadastral_document else None},
        "company": {
            "formation": {**(deed_document.get("verified_facts") or {}), "source": _source(deed_document) if deed_document else None},
            "register": {**(company_document.get("verified_facts") or {}), "source": _source(company_document) if company_document else None},
        },
        "harvest_declarations": harvest_declarations,
        "reconciliation": {
            "checks": checks,
            "all_required_checks_pass": all(checks.values()),
            "official_parcel_area_ha_in_database": db_official_ha,
            "operational_block_area_ha": block_area_ha,
            "warnings": warnings,
        },
        "documents": [_source(row) for row in prepared],
    }


def official_area_for(*, year: int | None = None, purpose: str = "productive") -> tuple[float | None, dict[str, Any]]:
    """Select an area by meaning, never by whichever table happens to be queried."""
    facts = authoritative_estate_facts(year)
    vineyard = facts["vineyard"]
    if purpose in {"treatment", "planted", "canopy"}:
        value = _number(vineyard.get("treatment_footprint_ha"))
        basis = "working_planted_area_pending_documentation"
    elif purpose == "registered":
        value = _number(vineyard.get("official_current_area_ha"))
        basis = "authoritative_registered_area"
    else:
        value = _number(vineyard.get("productive_area_ha_for_selected_year"))
        basis = "productive_area_for_selected_year"
    return value, {"basis": basis, "year": facts["as_of_year"], "source": vineyard.get("source"), "approximate": purpose in {"treatment", "planted", "canopy"} and bool(vineyard.get("pending_area_is_approximate"))}


def official_pipeline_context(year: int | None = None) -> dict[str, Any]:
    """Compact context safe to attach to AI, MCP and planning pipelines."""
    facts = authoritative_estate_facts(year)
    return {
        "authority_policy": facts["authority_policy"],
        "vineyard": facts["vineyard"],
        "reference_extracts": facts["reference_extracts"],
        "cadastral": facts["cadastral"],
        "harvest_declaration": facts["harvest_declarations"].get(str(facts["as_of_year"])),
        "company": facts["company"],
        "reconciliation": facts["reconciliation"],
    }
