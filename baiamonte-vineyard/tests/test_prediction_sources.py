from datetime import date
from pathlib import Path

import struct

from app.prediction_sources import ensemble_pick_window_adjustment, sentinel_index_statistics, summarize_ensemble, summarize_seasonal


def test_ensemble_summary_preserves_member_spread_and_probabilities():
    payload = {
        "model": "test",
        "hourly": {
            "time": ["2026-09-10T00:00", "2026-09-10T01:00"],
            "precipitation_member01": [0, 0],
            "precipitation_member02": [3, 3],
            "temperature_2m_member01": [34, 35],
            "temperature_2m_member02": [36, 37],
        },
    }
    result = summarize_ensemble(payload)
    day = result["days"][0]
    assert result["member_count"] == 2
    assert day["rain_probability_5mm_pct"] == 50
    assert day["heat_probability_35c_pct"] == 100
    assert day["rain_mm_p10"] < day["rain_mm_p90"]


def test_ensemble_adjustment_is_bounded_and_horizon_limited():
    context = {"open_meteo_ensemble": {"status": "fresh", "payload": {"days": [{"date": "2026-09-10", "rain_probability_5mm_pct": 80, "heat_probability_35c_pct": 0}]}}}
    adjustment, evidence = ensemble_pick_window_adjustment(context, date(2026, 9, 10), date(2026, 9, 1))
    assert adjustment == 1
    assert evidence["bounded_adjustment_days"] == 1
    adjustment, evidence = ensemble_pick_window_adjustment(context, date(2026, 10, 1), date(2026, 9, 1))
    assert adjustment == 0
    assert evidence["applied"] is False


def test_seasonal_summary_is_context_not_a_pick_date():
    result = summarize_seasonal({"daily": {"time": ["2026-09-01"], "temperature_2m_mean_member01": [20], "temperature_2m_mean_member02": [22], "precipitation_sum_member01": [1], "precipitation_sum_member02": [5]}})
    assert result["daily"][0]["temperature_c_median"] == 21
    assert "pick_date" not in result["daily"][0]


def test_seasonal_summary_tolerates_missing_member_and_mean_values():
    result = summarize_seasonal({"daily": {"time": ["2026-09-01"], "temperature_2m_mean": [None], "temperature_2m_mean_member01": [None], "precipitation_sum": [None], "precipitation_sum_member01": [None]}})
    assert result["daily"][0]["temperature_c_median"] is None
    assert result["daily"][0]["rain_mm_median"] is None


def test_sentinel_indices_are_cloud_masked_and_lai_is_labelled_estimate():
    # Six 1x2 uint16 bands: blue, red, red-edge, nir, SCL and data mask.
    header = "{'descr': '<u2', 'fortran_order': False, 'shape': (6, 1, 2), }"
    padding = 16 - ((10 + len(header) + 1) % 16)
    header_bytes = (header + " " * padding + "\n").encode()
    values = [1000, 1000, 2000, 2000, 3000, 3000, 6000, 6000, 4, 9, 1, 1]
    content = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header_bytes)) + header_bytes + struct.pack("<" + "H" * len(values), *values)
    result = sentinel_index_statistics(content)
    assert result["valid_pixels"] == 1
    assert result["ndvi"]["mean"] == .5
    assert "empirical estimate" in result["lai_method"]


def test_external_sources_cannot_enter_narrative_date_adjustment():
    source = (Path(__file__).resolve().parents[1] / "app" / "intelligence.py").read_text()
    assert 'if key != "external_prediction_sources"' in source
    assert '"ecmwf_seasonal": "early planning only; cannot move exact picking date"' in source


def test_regional_and_seasonal_labels_do_not_overstate_evidence():
    source = (Path(__file__).resolve().parents[1] / "app" / "prediction_sources.py").read_text()
    assert 'status = "historical_catalog_only" if latest else "no_data"' in source
    assert '"current_validation_available"] = False' in source
    assert "limited available-year baseline, not a 30-year climate normal" in source
