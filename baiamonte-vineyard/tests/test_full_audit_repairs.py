from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_disease_pressure_uses_daily_rain_not_repeated_observations():
    source = read("app/intelligence.py")
    function = source.split("def refresh_disease_pressure()", 1)[1].split("\ndef ", 1)[0]
    assert "FROM weather_daily" in function
    assert 'row["rainfall_source"] = "weather_daily"' in function
    assert "SUM(COALESCE(rain_mm,0)) rain_7d_mm" not in function
    assert "evidence-screen-v3" in function


def test_planned_empty_lots_cannot_override_physical_tank_contents():
    main = read("app/main.py")
    display = read("app/display_data.py")
    labels = read("app/tank_labels.py")
    occupancy_rule = "COALESCE(wx.volume_l,wx.initial_l,0)>0"
    assert occupancy_rule in main
    assert occupancy_rule in display
    assert labels.count(occupancy_rule) >= 3
    assert "COALESCE(w.volume_l,cp.manual_volume_l) volume_l" in labels
    assert "COALESCE(w.variety_summary,cp.manual_contents) variety_summary" in labels


def test_forecast_evidence_excludes_review_flagged_labs():
    source = read("app/historical_dashboard.py")
    assert "needs_review=0" in source
    assert '"laboratory_samples_excluded_for_review"' in source


def test_admin_exposes_operational_data_quality_snapshot():
    main = read("app/main.py")
    quality = read("app/data_quality.py")
    assert '"data_quality": operational_data_quality(estate_id())' in main
    for field in (
        "future_labor_records",
        "labs_missing_vintage",
        "labs_needing_review",
        "treatment_safety_gaps",
        "treatment_safety_restricted_records",
        "shared_planned_containers",
        "shared_occupied_containers",
    ):
        assert field in quality


def test_repeatable_live_audit_covers_high_risk_domains():
    audit = read("scripts/audit_live_integrity.sh")
    for check in (
        "payment_integrity",
        "data_quality",
        "duplicate_tank_ids",
        "duplicate_ids",
        "rainfall_source",
        "overdue_open",
        "unhealthy_processes",
    ):
        assert check in audit
