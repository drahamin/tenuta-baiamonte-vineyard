from unittest.mock import patch

from app.official_facts import authoritative_estate_facts, official_area_for


DOCUMENTS = [
    {"id": "old", "document_type": "vineyard_register", "title": "Complete", "status": "current", "verified_facts": {"official_vineyard_area_m2": 9144, "alicante_m2": 1626, "grecanico_m2": 3093, "nerello_mascalese_m2": 4425, "parcel_83_76_m2": 1685, "parcel_83_77_m2": 93, "parcel_83_93_m2": 7366}},
    {"id": "new", "document_type": "vineyard_register", "title": "Incomplete", "status": "reference", "verified_facts": {"reported_vineyard_area_m2": 5461, "coverage_status": "incomplete_new_system_extract"}},
]


def _one(sql, _params):
    if "evidence_references" in sql:
        return {"confidence": "high", "metadata": {"pending_new_planting_area_ha": .3, "working_total_planted_area_ha": 1.2144, "current_production_area_ha": .9144, "projected_productive_area_ha_2027": 1.2144, "expected_productive_year": 2027, "area_is_approximate": True}}
    if "cadastral_parcels" in sql:
        return {"official_vineyard_area_ha": .9144}
    if "vineyard_blocks" in sql:
        return {"operational_block_area_ha": 1.2144}
    return {}


@patch("app.official_facts.fetch_all", return_value=DOCUMENTS)
@patch("app.official_facts.fetch_one", side_effect=_one)
def test_authoritative_area_never_uses_incomplete_extract(_fetch_one, _fetch_all):
    facts = authoritative_estate_facts(2026)
    assert facts["vineyard"]["official_current_area_m2"] == 9144
    assert facts["reference_extracts"]["italy_new_system_vineyard_area_m2"] == 5461
    assert facts["vineyard"]["productive_area_ha_for_selected_year"] == .9144
    assert facts["vineyard"]["official_current_ha"] == .9144
    assert facts["vineyard"]["working_planted_ha"] == 1.2144
    assert facts["vineyard"]["parcel_vineyard_area_m2"] == {"83/76": 1685, "83/77": 93, "83/93": 7366}
    assert facts["reconciliation"]["all_required_checks_pass"] is True


@patch("app.official_facts.fetch_all", return_value=DOCUMENTS)
@patch("app.official_facts.fetch_one", side_effect=_one)
def test_area_is_selected_by_calculation_purpose(_fetch_one, _fetch_all):
    treatment, treatment_basis = official_area_for(year=2026, purpose="treatment")
    future_productive, productive_basis = official_area_for(year=2027, purpose="productive")
    assert treatment == 1.2144
    assert treatment_basis["approximate"] is True
    assert future_productive == 1.2144
    assert productive_basis["basis"] == "productive_area_for_selected_year"
