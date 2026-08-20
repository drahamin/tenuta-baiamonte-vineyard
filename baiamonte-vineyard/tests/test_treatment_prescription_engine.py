from datetime import date
from pathlib import Path

from app.domains.treatments import (
    _profile_ready,
    _review_possible_product,
    calculate_area_rate_quantity,
    calculate_area_mix,
    calculate_sprayer_batches,
    calculate_stock_shortage,
    calculate_water_rate_quantity,
    select_application_window,
)
from app.intelligence import predict_next_treatment


ROOT = Path(__file__).resolve().parents[1]


def test_area_rate_is_converted_to_total_and_per_100_l_tank_rate():
    result = calculate_area_mix(area_ha=.643, water_l=500, rate_kg_ha=2)
    assert result == {"area_ha": .643, "water_l": 500.0, "rate_kg_ha": 2, "total_kg": 1.286, "per_100_l_g": 257.2}


def test_needed_stock_is_only_the_positive_shortage():
    assert calculate_stock_shortage(1.286, 0) == 1.286
    assert calculate_stock_shortage(1.286, 1) == .286
    assert calculate_stock_shortage(1.286, 2) == 0


def test_water_application_is_split_into_documented_nominal_sprayer_fills():
    assert calculate_sprayer_batches(500, 200) == [
        {"batch": 1.0, "water_l": 200, "share": .4},
        {"batch": 2.0, "water_l": 200, "share": .4},
        {"batch": 3.0, "water_l": 100, "share": .2},
    ]
    assert calculate_sprayer_batches(500, None) == []
    assert calculate_sprayer_batches(400, 200) == [
        {"batch": 1.0, "water_l": 200, "share": .5},
        {"batch": 2.0, "water_l": 200, "share": .5},
    ]


def test_water_rate_quantity_scales_with_adjustable_carrier_volume():
    assert calculate_water_rate_quantity(water_l=200, rate_min=5, rate_max=5, rate_unit="g/L") == {
        "water_l": 200,
        "minimum": 1,
        "maximum": 1,
        "unit": "kg",
        "rate_min": 5,
        "rate_max": 5,
        "rate_unit": "g/L",
    }
    assert calculate_water_rate_quantity(water_l=400, rate_min=5, rate_max=5, rate_unit="g/L")["minimum"] == 2
    gel = calculate_water_rate_quantity(water_l=400, rate_min=100, rate_max=300, rate_unit="ml/100 L")
    assert gel["minimum"] == .4
    assert gel["maximum"] == 1.2
    assert gel["unit"] == "L"
    ferticus = calculate_water_rate_quantity(water_l=400, rate_min=300, rate_max=500, rate_unit="g/100 L")
    assert ferticus["minimum"] == 1.2
    assert ferticus["maximum"] == 2
    assert ferticus["unit"] == "kg"


def test_area_rate_quantity_preserves_liquid_units_and_projects_the_estate_range():
    assert calculate_area_rate_quantity(area_ha=.643, rate_min=1, rate_max=3, rate_unit="L/ha") == {
        "area_ha": .643,
        "minimum": .643,
        "maximum": 1.929,
        "unit": "L",
        "rate_min": 1,
        "rate_max": 3,
        "rate_unit": "L/ha",
    }


def test_per_hectare_support_product_gets_a_quantity_without_density_guessing():
    row = {
        "product_name": "REPENTE",
        "mixture_role": "support",
        "default_decision": "not_selected",
        "profile_id": "profile",
        "final_application_medium": "water_spray",
        "verification_status": "verified",
        "estate_authorization_status": "confirmed",
        "eligible_for_projection": 1,
        "minimum_rate_per_ha": 1,
        "maximum_rate_per_ha": 3,
        "minimum_rate_per_ha_unit": "L/ha",
        "compatibility_status": "conditional",
    }
    result = _review_possible_product(row, {}, planning_area_ha=.643)
    assert result["projected_quantity"]["minimum"] == .643
    assert result["projected_quantity"]["maximum"] == 1.929
    assert result["projected_quantity"]["unit"] == "L"


def test_projection_requires_verified_water_spray_formulation():
    assert _profile_ready({"final_application_medium": "water_spray", "verification_status": "verified", "estate_authorization_status": "confirmed", "eligible_for_projection": 1})
    assert not _profile_ready({"final_application_medium": "water_spray", "verification_status": "needs_container_label", "estate_authorization_status": "confirmed", "eligible_for_projection": 1})
    assert not _profile_ready({"final_application_medium": "water_spray", "verification_status": "verified", "estate_authorization_status": "not_confirmed", "eligible_for_projection": 1})
    assert not _profile_ready({"final_application_medium": "water_spray", "verification_status": "verified", "estate_authorization_status": "confirmed", "eligible_for_projection": 0})
    assert not _profile_ready({"final_application_medium": "fertigation", "verification_status": "verified", "estate_authorization_status": "confirmed", "eligible_for_projection": 1})


def test_resolve_projects_powder_quantity_from_adjustable_water_volume():
    row = {
        "product_name": "RESOLVE",
        "mixture_role": "support",
        "default_decision": "not_selected",
        "profile_id": "profile",
        "concentrate_form": "water_soluble_powder",
        "final_application_medium": "water_spray",
        "verification_status": "verified",
        "estate_authorization_status": "confirmed",
        "eligible_for_projection": 1,
        "selection_conditions": "Use only with agronomist approval.",
        "water_rate_min": 5,
        "water_rate_max": 5,
        "water_rate_unit": "g/L",
        "compatibility_status": "not_verified",
        "compatibility_conditions": "Keep separate unless approved.",
    }
    result = _review_possible_product(row, {"RESOLVE": {"stock_on_hand": 10, "unit": "kg"}}, planning_water_l=400)
    assert result["decision"] == "not_selected"
    assert result["stock_on_hand"] == 10
    assert result["projected_quantity"]["minimum"] == 2
    assert result["projected_quantity"]["maximum"] == 2
    assert result["projected_quantity"]["unit"] == "kg"


def test_sulfur_window_rejects_rain_heat_and_high_wind():
    result = select_application_window([
        {"datetime": "2026-08-22", "temperature": 27, "precipitation": 1.5, "wind_speed": 8},
        {"datetime": "2026-08-23", "temperature": 31, "precipitation": 0, "wind_speed": 8},
        {"datetime": "2026-08-24", "temperature": 27, "precipitation": 0, "wind_speed": 18},
    ], date(2026, 8, 22), date(2026, 8, 26), sulfur=True)
    assert result["status"] == "no_suitable_window"
    assert result["recommended_date"] is None


def test_overdue_plan_keeps_current_disease_target_for_new_engine():
    result = predict_next_treatment(
        [{"id": "t5", "status": "planned", "purpose": "Treatment 5", "planned_application_date": "2026-06-26"}],
        [{"id": "pressure", "disease_code": "powdery_mildew", "disease_name": "Powdery mildew", "risk_score": 37.5, "risk_level": "moderate", "input_snapshot": {"weather_observation_count": 554, "temp_avg_c": 24.3}}],
        date(2026, 8, 19),
    )
    assert result["type"] == "overdue_verification"
    assert result["target_code"] == "powdery_mildew"
    assert result["current_risk_score"] == 37.5


def test_purchase_and_label_migration_is_auditable_and_resets_treatment_five():
    migration = (ROOT / "db/migrations/066_treatment_prescription_engine.sql").read_text(encoding="utf-8")
    for invoice, product, quantity in [
        ("1478", "SACRON 45 WG", "1,'kg'"),
        ("1478", "OSSICLOR 35 WG", "10,'kg'"),
        ("1919", "IMPULSIVE", "5,'L'"),
        ("1919", "RESOLVE", "5,'L'"),
        ("1919", "TERRAPLUS SOLUB", "15,'kg'"),
        ("1919", "GEL DI SILICE", "5,'kg'"),
    ]:
        assert invoice in migration
        assert product in migration
        assert quantity in migration
    assert "authorization_status='expired'" in migration
    assert "authorization_expires_on='2026-08-15'" in migration
    assert "LOWER(TRIM(purpose))='treatment 5' AND status='planned'" in migration
    assert "status='cancelled'" in migration
    assert "This is not a completed application" in migration


def test_invoice_quantities_are_posted_as_stock_receipts():
    migration = (ROOT / "db/migrations/067_invoice_stock_receipts.sql").read_text(encoding="utf-8")
    assert "'purchase',x.quantity" in migration
    assert "'invoice_stock',x.purchase_evidence_id" in migration
    for product, quantity in [("SACRON 45 WG", "1 quantity"), ("OSSICLOR 35 WG", "10,6.9550"), ("IMPULSIVE PREMIUM", "5,16.5380"), ("RESOLVE", "10,15.9620"), ("TERRAPLUS SOLUB NPK 8-7-6", "15,3.7180"), ("GEL DI SILICE", "5,9.8360")]:
        assert product in migration
        assert quantity in migration
    guidance = (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
    assert "GREATEST(0,SUM(i.quantity_delta)) stock_on_hand" in guidance
    assert '"in_stock"' in guidance
    assert '"insufficient_stock"' in guidance


def test_treatment_reference_migration_preserves_products_sources_and_sprayer_constraints():
    migration = (ROOT / "db/migrations/072_treatment_product_reference.sql").read_text(encoding="utf-8")
    for table in [
        "treatment_product_profiles",
        "treatment_product_options",
        "treatment_product_evidence",
        "treatment_regulatory_sources",
        "spray_equipment_profiles",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "final_application_medium ENUM('water_spray')" in migration
    assert "estate_authorization_status ENUM('confirmed','not_confirmed')" in migration
    assert "owner-confirmed:2026-08-20" in migration
    assert "water_dispersible_granule" in migration
    assert "density_kg_l" in migration
    assert "density or unit conversion" in migration
    assert "historical_application" in migration
    assert "official_register" in migration
    assert "ministry-open-data:2026-08-17:001583" in migration
    assert "ministry-open-data:2026-08-17:012759" in migration
    assert "ministry-open-data:2026-08-17:012916" in migration
    assert "ministry-open-data:2026-08-17:012723" in migration
    assert "OSSICLOR 20 BLU FLOW" in migration
    assert "container-label:repente:lot-25642111E1" in migration
    assert "container-label:impulsive-premium-f:lot-120751001C1" in migration
    assert "container-label:gel-di-silice:lot-26271001E2" in migration
    assert "do not report the product as expired" in migration
    assert "tank_capacity_l,calibration_status" in migration
    assert "'water_spray',200,'needs_measurement'" in migration
    assert "actual usable fill" in migration
    assert "technical_product_page" in migration
    assert "https://www.agricolaalbese.it/kalos-resolve-biostimolante-5-kg-bio.html" in migration
    assert "water-dispersible powder" in migration
    assert "o.water_rate_min=5" in migration
    assert "o.minimum_rate_per_ha=2" in migration
    assert "Sulfur and copper products must remain separate" in migration


def test_guidance_reads_possible_products_and_mixing_rules_from_database():
    guidance = (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
    assert "FROM treatment_product_options" in guidance
    assert "FROM treatment_product_profiles" in guidance
    assert "FROM spray_equipment_profiles" in guidance
    assert '"GEL DI SILICE", "purchase_state"' not in guidance
    assert "candidate.get(\"mixing_instructions\")" in guidance
    assert "equipment_selector" in guidance
    assert "equipment_choices" in guidance


def test_projection_configuration_is_exposed_as_home_assistant_addon_options():
    configuration = (ROOT / "config.yaml").read_text(encoding="utf-8")
    settings = (ROOT / "app/config.py").read_text(encoding="utf-8")
    migration = (ROOT / "db/migrations/075_treatment_projection_configuration.sql").read_text(encoding="utf-8")
    for key in ["treatment_planning_water_l", "treatment_default_sprayer"]:
        assert key in configuration
        assert key in settings
    assert "IMPULSIVE PREMIUM" in migration
    assert "REPENTE" in migration
    assert "maximum_rate_per_ha" in migration


def test_current_direction_enrichment_unblocks_verified_support_and_liquid_primary_products():
    migration = (ROOT / "db/migrations/076_complete_treatment_product_directions.sql").read_text(encoding="utf-8")
    assert "0.75-1.00 L/ha" in migration
    assert "300-500 g/hL" in migration
    assert "water_rate_unit ENUM('g/L','g/100 L','ml/100 L')" in migration
    assert "localized soil spraying" in migration
    assert "o.minimum_rate_per_ha=15,o.maximum_rate_per_ha=30" in migration
    assert "Do not spray the canopy" in migration
    assert "1.7,4.2,'L/ha',21,8,'M01'" in migration
    assert "registration 012723 through 2029-06-30" in migration
