from datetime import date
from pathlib import Path

from app.domains.treatments import (
    _additional_disease_controls,
    _historical_rate_total,
    _support_program_selection,
    _profile_ready,
    _review_possible_product,
    calculate_area_rate_quantity,
    calculate_area_mix,
    calculate_batch_recipe,
    build_one_pass_treatment_plan,
    agronomist_program_backtest,
    calculate_sprayer_batches,
    calculate_stock_shortage,
    treatment_inventory_plan,
    calculate_water_rate_quantity,
    compare_treatment_programs,
    reconcile_area_and_water_rate,
    select_application_window,
    select_agronomist_program_analog,
    treatment_program_similarity,
    treatment_weather_similarity,
)
from app.intelligence import _weather_learning_similarity, predict_next_treatment


ROOT = Path(__file__).resolve().parents[1]


def test_area_rate_is_converted_to_total_and_per_100_l_tank_rate():
    result = calculate_area_mix(area_ha=.643, water_l=500, rate_kg_ha=2)
    assert result == {"area_ha": .643, "water_l": 500.0, "rate_kg_ha": 2, "total_kg": 1.286, "per_100_l_g": 257.2}


def test_dual_rate_screen_caps_area_rate_at_the_label_water_concentration():
    result = reconcile_area_and_water_rate(
        area_ha=.643, water_l=400, selected_rate=4, minimum_rate=1.7, maximum_rate=4.2,
        rate_unit="L/ha", water_rate_min=170, water_rate_max=420, water_rate_unit="ml/100 L",
    )
    assert result["valid"] is True
    assert result["total"] == 1.68
    assert result["per_100_l"] == 420
    assert result["limited_by_water_concentration"] is True


def test_replay_comparison_explains_same_target_alternative_and_support_products():
    result = compare_treatment_programs(
        [{"product_name": "OSSICLOR 20 BLU FLOW", "program_role": "primary disease control"}],
        [{"products": [
            {"product_name": "SACRON 45 WG", "product_type": "plant_protection", "authorized_targets": "downy_mildew", "mixture_roles": "primary", "dose_amount": 80, "dose_unit": "g/100 L"},
            {"product_name": "FERTICUS 18 M", "product_type": "fertilizer", "authorized_targets": "", "mixture_roles": "nutrition", "dose_amount": 350, "dose_unit": "g/100 L"},
        ]}], target_code="downy_mildew",
    )
    assert result["actual_record_found"] is True
    assert result["agreement_count"] == 0
    assert result["system_only_count"] == 1
    assert result["actual_only_count"] == 2
    by_name = {row["product_name"]: row for row in result["rows"]}
    assert "same target" in by_name["SACRON 45 WG"]["explanation"]
    assert "nutritional/support" in by_name["FERTICUS 18 M"]["explanation"]


def test_needed_stock_is_only_the_positive_shortage():
    assert calculate_stock_shortage(1.286, 0) == 1.286
    assert calculate_stock_shortage(1.286, 1) == .286
    assert calculate_stock_shortage(1.286, 2) == 0


def test_simulation_inventory_plan_shows_required_stock_and_negative_receipt_gap():
    result = treatment_inventory_plan([
        {"product_name": "OSSICLOR 20 BLU FLOW", "total": 1.1, "total_unit": "L", "stock_on_hand": -1.429, "stock_unit": "L"},
        {"product_name": "MICROTHIOL", "total": .8, "total_unit": "kg", "stock_on_hand": 1200, "stock_unit": "g"},
    ])
    assert result[0]["status"] == "receipt_pending"
    assert result[0]["remaining_needed"] == 2.529
    assert result[1]["status"] == "ready"
    assert result[1]["balance_after_treatment"] == .4


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


def test_each_sprayer_fill_gets_a_complete_readable_ingredient_recipe():
    batches = calculate_sprayer_batches(500, 200)
    recipe = calculate_batch_recipe(
        batches,
        [
            {"product_name": "MICROTHIOL DISPERSS", "total": 1.286, "total_unit": "kg"},
            {"product_name": "FRONTIERE", "total": .75, "total_unit": "L"},
        ],
    )
    assert [row["water_l"] for row in recipe] == [200, 200, 100]
    assert [row["components"][0]["display_quantity"] for row in recipe] == [514.4, 514.4, 257.2]
    assert [row["components"][0]["display_unit"] for row in recipe] == ["g", "g", "g"]
    assert [row["components"][1]["display_quantity"] for row in recipe] == [300, 300, 150]
    assert [row["components"][1]["display_unit"] for row in recipe] == ["ml", "ml", "ml"]
    assert round(sum(row["components"][0]["quantity"] for row in recipe), 6) == 1.286
    assert round(sum(row["components"][1]["quantity"] for row in recipe), 6) == .75


def test_one_pass_plan_splits_every_necessary_product_into_two_200_l_batches():
    plan = build_one_pass_treatment_plan(
        water_l=400,
        batches=calculate_sprayer_batches(400, 200),
        components=[
            {"product_name": "Control A", "total": 1.2, "total_unit": "kg", "mixing_position": 1, "application_relationship": "primary_pass"},
            {"product_name": "Control B", "total": .8, "total_unit": "L", "mixing_position": 2, "application_relationship": "same_tank_verified"},
        ],
    )
    assert plan["application_passes"] == 1
    assert plan["total_carrier_l"] == 400
    assert plan["batch_count"] == 2
    assert plan["batch_capacity_l"] == 200
    assert plan["same_recipe_each_batch"] is True
    assert [item["display_quantity"] for item in plan["batch_recipe"][0]["components"]] == [600, 400]
    assert [item["display_unit"] for item in plan["batch_recipe"][0]["components"]] == ["g", "ml"]
    assert plan["mix_status"] == "ready_for_final_agronomist_review"


def test_one_pass_plan_marks_unverified_combined_product_for_review():
    plan = build_one_pass_treatment_plan(
        water_l=400,
        batches=calculate_sprayer_batches(400, 200),
        components=[{"product_name": "Support", "total": 1, "total_unit": "L", "application_relationship": "separate_pass_or_agronomist_mix_review"}],
    )
    assert plan["application_passes"] == 1
    assert plan["mix_status"] == "exact_mix_review_required"
    assert plan["compatibility_review_products"] == ["Support"]


def test_historical_agronomist_rate_is_scaled_to_current_two_batch_process():
    assert _historical_rate_total(450, "g/100 L", 400) == (1.8, "kg")
    assert _historical_rate_total(300, "ml/100 L", 400) == (1.2, "L")


def test_complete_program_similarity_scores_products_not_duplicate_rows():
    score = treatment_program_similarity(
        ["Microthiol", "Frontiere", "Frontiere", "Sacron"],
        ["Microthiol", "Frontiere", "Repente"],
    )
    assert score == {
        "agreement_count": 2,
        "actual_count": 3,
        "predicted_count": 3,
        "recall_pct": 66.7,
        "precision_pct": 66.7,
        "similarity_pct": 50.0,
    }


def test_agronomist_pattern_backtest_leaves_the_answer_out():
    programs = [
        {"id": "t2", "purpose": "Treatment 2", "application_date": date(2026, 5, 19), "items": [{"product_name": name} for name in ["A", "B", "C", "D", "E"]]},
        {"id": "t3", "purpose": "Treatment 3", "application_date": date(2026, 5, 8), "items": [{"product_name": name} for name in ["A", "B", "C", "D", "F", "G"]]},
        {"id": "t4", "purpose": "Treatment 4", "application_date": date(2026, 6, 17), "items": [{"product_name": name} for name in ["H", "I", "J", "K", "L", "M"]]},
        {"id": "t5", "purpose": "Treatment 5", "application_date": date(2026, 6, 27), "items": [{"product_name": name} for name in ["H", "I", "J", "K", "L", "M"]]},
    ]
    selected = select_agronomist_program_analog(
        programs, scenario_day=date(2026, 6, 27), exclude_id="t5"
    )
    assert selected["id"] == "t4"
    validation = agronomist_program_backtest(programs)
    assert validation["replay_count"] == 4
    assert validation["exact_program_count"] == 2
    assert validation["average_recall_pct"] == 86.7
    assert "never used as its own prediction" in validation["method"]


def test_agronomist_pattern_uses_weather_before_calendar_proximity():
    current = {"temp_avg_c": 20, "temp_max_c": 26, "humidity_avg_pct": 82, "rain_72h_mm": 12, "rain_7d_mm": 22}
    programs = [
        {
            "id": "calendar-close", "purpose": "Dry treatment", "application_date": date(2026, 6, 20),
            "learning_weather_snapshot": {"temp_avg_c": 29, "temp_max_c": 38, "humidity_avg_pct": 40, "rain_72h_mm": 0, "rain_7d_mm": 0},
        },
        {
            "id": "weather-close", "purpose": "Wet treatment", "application_date": date(2026, 5, 25),
            "learning_weather_snapshot": {"temp_avg_c": 21, "temp_max_c": 27, "humidity_avg_pct": 80, "rain_72h_mm": 11, "rain_7d_mm": 24},
        },
    ]
    selected = select_agronomist_program_analog(
        programs, scenario_day=date(2026, 6, 22), weather_context=current
    )
    assert selected["id"] == "weather-close"
    assert selected["weather_match"]["similarity_pct"] > 90


def test_weather_similarity_requires_only_comparable_recorded_markers():
    result = treatment_weather_similarity(
        {"temp_avg_c": 20, "humidity_avg_pct": 80, "rain_7d_mm": 20},
        {"temp_avg_c": 21, "humidity_avg_pct": 75, "rain_7d_mm": 25, "soil_moisture_avg_pct": None},
    )
    assert result["comparable_metrics"] == 3
    assert result["similarity_pct"] == 87.8
    assert _weather_learning_similarity(
        {"temp_avg_c": 20, "humidity_avg_pct": 80, "rain_7d_mm": 20},
        {"temp_avg_c": 21, "humidity_avg_pct": 75, "rain_7d_mm": 25},
    ) == (87.8, 3)


def test_completed_treatments_persist_weather_learning_and_refresh_the_model():
    migration = (ROOT / "db/migrations/115_treatment_weather_learning.sql").read_text(encoding="utf-8")
    intelligence = (ROOT / "app/intelligence.py").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    for field in ["application_id", "weather_snapshot", "pressure_snapshot", "products_snapshot", "program_signature", "learning_status"]:
        assert field in migration
    assert "def refresh_treatment_weather_learning" in intelligence
    assert "Uses only weather through the day before each completed treatment" in intelligence
    assert "refresh_treatment_weather_learning(treatment_id)" in main
    assert "closest_treatment_weather_learning(highest)" in intelligence


def test_simulator_gates_terraplus_to_mapped_young_vines_with_current_need():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/treatment-tools.js").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/treatment_routes.py").read_text(encoding="utf-8")
    guidance = (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
    assert 'name="block_id"' in html
    assert 'name="nutrition_signal"' in html
    assert "weak_growth" in html and "verified_deficiency" in html
    assert 'prediction["selected_block"] = selected_block' in routes
    assert 'prediction["nutrition_signal"] = nutrition_signal' in routes
    assert '"recommended_for_agronomist_review" if young_block and nutrition_signal != "none"' in guidance
    assert "separate root-zone/fertigation application" in guidance
    assert "young_vine_nutrition" in script


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


def test_weather_driven_pressure_does_not_invent_a_support_product_need():
    reviews = [
        {
            "product_name": "FRONTIERE", "target_code": "any", "mixture_role": "support",
            "decision": "not_selected", "compatibility_status": "conditional",
            "projected_quantity": {"minimum": .45, "maximum": .6, "unit": "L"},
        },
        {
            "product_name": "REPENTE", "target_code": "any", "mixture_role": "support",
            "decision": "not_selected", "compatibility_status": "conditional",
            "projected_quantity": {"minimum": .6, "maximum": 1.8, "unit": "L"},
        },
    ]
    selected = _support_program_selection(reviews, {
        "target_code": "downy_mildew", "current_risk_level": "high", "event_type": "heavy_rain",
    })
    assert selected == []


def test_visible_stress_signal_can_promote_a_separate_support_review():
    selected = _support_program_selection([{
        "product_name": "REPENTE", "target_code": "any", "mixture_role": "support",
        "decision": "not_selected", "compatibility_status": "conditional",
        "projected_quantity": {"minimum": .6, "maximum": 1.8, "unit": "L"},
    }], {
        "target_code": "downy_mildew", "current_risk_level": "moderate", "event_type": "visible_symptoms",
    })
    assert len(selected) == 1
    assert selected[0]["product_name"] == "REPENTE"
    assert selected[0]["selected_total"] == .6


def test_prior_use_alone_does_not_create_a_support_or_nutrition_recommendation():
    reviews = [
        {"product_name": "REPENTE", "target_code": "any", "mixture_role": "support", "decision": "not_selected", "compatibility_status": "conditional", "projected_quantity": {"minimum": .6, "maximum": 1.8, "unit": "L"}},
        {"product_name": "FRONTIERE", "target_code": "any", "mixture_role": "support", "decision": "not_selected", "compatibility_status": "conditional", "projected_quantity": {"minimum": .45, "maximum": .6, "unit": "L"}},
        {"product_name": "IMPULSIVE PREMIUM", "target_code": "any", "mixture_role": "nutrition", "decision": "not_selected", "compatibility_status": "conditional", "projected_quantity": {"minimum": 1.2, "maximum": 1.8, "unit": "L"}},
    ]
    selected = _support_program_selection(reviews, {
        "target_code": "downy_mildew", "current_risk_level": "moderate", "event_type": "heavy_rain",
        "historical_replay": True,
        "historical_context": {
            "effective_growth_stage": "shoot_growth",
            "previous_treatments": [{"source_products": "REPENTE\nFRONTIERE\nIMPULSIVE PREMIUM"}],
        },
    })
    assert selected == []


def test_nutrition_is_not_promoted_outside_the_growing_stage_even_with_prior_use():
    selected = _support_program_selection([{
        "product_name": "IMPULSIVE PREMIUM", "target_code": "any", "mixture_role": "nutrition",
        "decision": "not_selected", "compatibility_status": "not_verified",
        "projected_quantity": {"minimum": 1.2, "maximum": 1.8, "unit": "L"},
    }], {
        "target_code": "downy_mildew", "current_risk_level": "moderate", "event_type": "heavy_rain",
        "historical_replay": True,
        "historical_context": {
            "effective_growth_stage": "dormancy",
            "previous_treatments": [{"source_products": "IMPULSIVE PREMIUM"}],
        },
    })
    assert selected == []


def test_independent_moderate_secondary_pressure_adds_a_separate_disease_control(monkeypatch):
    candidate = {
        "product_name": "MICROTHIOL DISPERSS", "active_ingredient": "Sulfur 80%",
        "authorization_status": "authorized", "authorization_expires_on": date(2027, 7, 31),
        "target_name": "Powdery mildew", "min_dose": 2.0, "max_dose": 4.0,
        "dose_unit": "kg/ha", "water_rate_min": None, "water_rate_max": None,
        "water_rate_unit": None, "phi_days": 5, "unit": "kg",
        "final_application_medium": "water_spray", "verification_status": "verified",
        "estate_authorization_status": "confirmed", "eligible_for_projection": 1,
    }
    monkeypatch.setattr("app.domains.treatments.fetch_all", lambda *_args, **_kwargs: [candidate])
    controls = _additional_disease_controls(
        crop_scope="vineyard",
        prediction={
            "scenario_date": date(2026, 5, 19),
            "historical_context": {
                "effective_growth_stage": "shoot_growth",
                "pressure_screen": [{"disease_code": "powdery_mildew", "risk_score": 58, "risk_level": "moderate"}],
            },
        },
        primary_target="downy_mildew", area_ha=.6, water_l=400,
        stock_by_product={"MICROTHIOL DISPERSS": {"stock_on_hand": 4, "ledger_balance": 4, "unit": "kg"}},
        authorization_reference_day=date(2026, 5, 19),
    )
    assert len(controls) == 1
    assert controls[0]["product_name"] == "MICROTHIOL DISPERSS"
    assert controls[0]["program_role"] == "secondary disease control · powdery mildew"
    assert controls[0]["application_relationship"] == "separate_pass_pending_exact_mix_review"


def test_low_secondary_pressure_does_not_add_a_product(monkeypatch):
    monkeypatch.setattr("app.domains.treatments.fetch_all", lambda *_args, **_kwargs: [])
    controls = _additional_disease_controls(
        crop_scope="vineyard",
        prediction={
            "scenario_date": date(2026, 5, 19),
            "historical_context": {
                "effective_growth_stage": "shoot_growth",
                "pressure_screen": [{"disease_code": "powdery_mildew", "risk_score": 13.3, "risk_level": "low"}],
            },
        },
        primary_target="downy_mildew", area_ha=.6, water_l=400,
        stock_by_product={}, authorization_reference_day=date(2026, 5, 19),
    )
    assert controls == []


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


def test_historical_replay_preserves_selected_date_without_claiming_weather_clearance():
    result = select_application_window([
        {"date": "2026-06-17", "temperature_high": 29.2, "precipitation": 5.8, "wind_speed_kph": None},
    ], date(2026, 6, 17), date(2026, 6, 17), evidence_kind="historical_observation")
    assert result["status"] == "historical_replay_not_cleared"
    assert result["recommended_date"] == date(2026, 6, 17)
    assert "not an application authorization" in result["message"]


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
    assert "SUM(i.quantity_delta) stock_on_hand" in guidance
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


def test_sprayer_profile_can_be_configured_and_requires_complete_verified_measurements():
    routes = (ROOT / "app/domains/treatment_routes.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/treatment-tools.js").read_text(encoding="utf-8")
    assert '@router.get("/api/v1/treatments/sprayers"' in routes
    assert '@router.post("/api/v1/treatments/sprayers"' in routes
    assert "Verified calibration requires date, usable fill, nozzle setup, flow, pressure, speed, and carrier rate" in routes
    assert 'id="sprayerConfigForm"' in html
    for field in ["tank_capacity_l", "usable_capacity_l", "nozzle_setup", "flow_l_min", "operating_pressure_bar", "travel_speed_kph", "carrier_rate_l_ha"]:
        assert field in html
    assert "loadSprayerConfiguration" in script


def test_projection_configuration_is_exposed_as_home_assistant_addon_options():
    configuration = (ROOT / "config.yaml").read_text(encoding="utf-8")
    settings = (ROOT / "app/config.py").read_text(encoding="utf-8")
    migration = (ROOT / "db/migrations/075_treatment_projection_configuration.sql").read_text(encoding="utf-8")
    for key in ["treatment_planning_water_l", "treatment_default_sprayer", "treatment_sprayer_tank_capacity_l", "treatment_sprayer_carrier_rate_l_ha"]:
        assert key in configuration
        assert key in settings
    assert "IMPULSIVE PREMIUM" in migration
    assert "REPENTE" in migration
    assert "maximum_rate_per_ha" in migration
    routes = (ROOT / "app/domains/treatment_routes.py").read_text(encoding="utf-8")
    assert 'runtime_option("treatment_default_sprayer", settings.treatment_default_sprayer)' in routes


def test_second_owner_confirmed_sprayer_is_seeded_without_invented_calibration():
    migration = (ROOT / "db/migrations/089_fuxtec_msp22_sprayer.sql").read_text(encoding="utf-8")
    assert "FUXTEC FX-MSP2.2" in migration
    assert "tank_capacity_l,calibration_status" in migration
    assert "26,'needs_measurement'" in migration
    assert "carrier L/ha require field calibration" in migration


def test_primary_gs_sprayer_and_owner_confirmed_options_are_recorded():
    migration = (ROOT / "db/migrations/090_primary_gs_sprayer_specification.sql").read_text(encoding="utf-8")
    for code in ["M2192017.1", "M2400050", "M2030102.1"]:
        assert code in migration
    for specification in ["AR 252", "Honda GP160", "25 L/min", "30 bar", "200 L"]:
        assert specification in migration
    assert "not measured nozzle flow or operating pressure" in migration


def test_primary_sprayer_carrier_is_a_separate_linked_asset():
    migration = (ROOT / "db/migrations/091_bluebird_carrier_500h.sql").read_text(encoding="utf-8")
    for fact in ["Blue Bird Carrier 500 H", "885160", "Loncin 196 cc", "6.5 hp", "500 kg", "180 mm", "256.5 kg"]:
        assert fact in migration
    assert "crawler_carrier" in migration
    assert "recorded as a separate estate asset" in migration


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
