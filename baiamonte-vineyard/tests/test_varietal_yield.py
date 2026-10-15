from app.varietal_yield import build_varietal_yield_profiles, is_blended_summary, variety_key


def test_variety_key_normalizes_operational_and_legal_grenache_names():
    assert variety_key("Grenache") == "grenache"
    assert variety_key("Alicante") == "grenache"
    assert variety_key("Alicante / Grenache") == "grenache"


def test_named_blend_is_not_used_as_single_variety_training_evidence():
    assert is_blended_summary("Mamma Fiamma · Nerello Mascalese / Grenache blend") is True
    profiles = build_varietal_yield_profiles(
        2026,
        [
            {"vintage_year": 2024, "variety_name": "Mamma Fiamma · Nerello Mascalese / Grenache blend", "grapes_kg": 1558, "wine_l": 881},
            {"vintage_year": 2025, "variety_name": "Nerello Mascalese", "grapes_kg": 3000, "wine_l": 2100},
        ],
        [],
        [],
        fallback_l_per_kg=0.67,
    )
    assert profiles["nerello mascalese"]["historical_vintages"] == [2025]
    assert profiles["nerello mascalese"]["predictive_l_per_kg"] == 0.7
    assert "grenache" not in profiles


def test_profiles_learn_weighted_prior_vintage_ratio_and_keep_current_observation_separate():
    profiles = build_varietal_yield_profiles(
        2026,
        [
            {"vintage_year": 2024, "variety_name": "Grecanico", "grapes_kg": 1000, "wine_l": 600},
            {"vintage_year": 2025, "variety_name": "Grecanico", "grapes_kg": 2000, "wine_l": 1400},
        ],
        [{"variety_name": "Grecanico", "grape_kg": 2500, "estate_fruit_kg": 2500}],
        [{"variety_name": "Grecanico", "measured_wine_l": 1500, "initial_liquid_l": 1600}],
        fallback_l_per_kg=0.7,
    )
    profile = profiles["grecanico"]
    assert profile["predictive_l_per_kg"] == 0.666667
    assert profile["current_observed_l_per_kg"] == 0.6
    assert profile["initial_observed_l_per_kg"] == 0.64
    assert profile["predicted_l_from_received_grapes"] == 1666.667
    assert profile["predicted_full_bottles_from_received_grapes"] == 2222
    assert profile["historical_vintages"] == [2024, 2025]
    assert profile["historical_results"][0]["observed_l_per_kg"] == 0.6
    assert profile["historical_results"][1]["full_bottles_750ml"] == 1866


def test_profile_override_wins_without_training_on_current_vintage():
    profiles = build_varietal_yield_profiles(
        2026,
        [{"vintage_year": 2026, "variety_name": "Grenache", "grapes_kg": 1000, "wine_l": 1000}],
        [{"variety_name": "Alicante", "fruit_kg": 1078, "purchased_fruit_kg": 1078}],
        [],
        fallback_l_per_kg=0.7,
        overrides={"Grenache": 0.68},
    )
    profile = profiles["grenache"]
    assert profile["predictive_l_per_kg"] == 0.68
    assert profile["prediction_is_configured"] is True
    assert profile["historical_vintage_count"] == 0
    assert profile["predicted_l_from_received_grapes"] == 733.04
