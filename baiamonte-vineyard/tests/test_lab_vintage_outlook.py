from __future__ import annotations

from pathlib import Path

import pytest

from app.domains import laboratory
from app.domains.laboratory import _canonical_sample_name, _direction_matches, _lab_current_finding, _project_lab_series, _variety_lab_standards


def result(
    vintage: int,
    lab_date: str,
    value: float,
    *,
    sample: str = "Nerello",
    sample_type: str = "wine",
    stage: str = "aging",
    analyte: str = "malic_acid",
    unit: str = "g/L",
    target_min: float | None = None,
    target_max: float | None = None,
) -> dict:
    return {
        "result_id": f"{sample}-{stage}-{unit}-{lab_date}-{value}",
        "sample_name": sample,
        "sample_type": sample_type,
        "stage": stage,
        "analyte_code": analyte,
        "analyte_name": "Malic acid",
        "unit": unit,
        "vintage_year": vintage,
        "lab_date": lab_date,
        "numeric_value": value,
        "comparison_flag": "within",
        "target_min": target_min,
        "target_max": target_max,
        "source_reference": "Approved enology range",
        "needs_review": False,
    }


def test_projection_uses_each_prior_vintage_endpoint_not_all_readings() -> None:
    rows = [
        result(2024, "2024-10-01", 2.0),
        result(2024, "2024-10-11", 3.0),
        result(2025, "2025-10-01", 2.2),
        result(2025, "2025-10-11", 3.4),
        result(2026, "2026-10-01", 2.1),
        result(2026, "2026-10-11", 3.5),
    ]

    projection = _project_lab_series(rows, 2026)[0]

    assert projection["historical_endpoint_average"] == pytest.approx(3.2)
    assert projection["same_relative_day_average"] == pytest.approx(3.2)
    assert projection["projection_adjustment"] == pytest.approx(0.3)
    assert projection["projected_endpoint"] == pytest.approx(3.5)
    assert projection["projected_endpoint_date"] == "2026-10-11"
    assert projection["projection_low"] == pytest.approx(3.3)
    assert projection["projection_high"] == pytest.approx(3.7)


def test_projection_never_mixes_wines_stages_or_units() -> None:
    rows = [
        result(2025, "2025-10-01", 1.0),
        result(2026, "2026-10-01", 1.5),
        result(2025, "2025-10-01", 90.0, sample="Grecanico"),
        result(2025, "2025-10-01", 80.0, stage="fermentation"),
        result(2025, "2025-10-01", 70.0, unit="mg/L"),
    ]

    projections = _project_lab_series(rows, 2026)

    assert len(projections) == 1
    assert projections[0]["sample_name"] == "Nerello Mascalese"
    assert projections[0]["stage"] == "aging"
    assert projections[0]["unit"] == "g/L"
    assert projections[0]["historical_endpoint_average"] == pytest.approx(1.0)
    assert projections[0]["projected_endpoint"] == pytest.approx(1.5)


def test_projection_matches_safe_vintage_and_spelling_aliases() -> None:
    rows = [
        result(2023, "2023-10-01", 1.0, sample="Grecanico"),
        result(2024, "2024-10-01", 1.2, sample="Bianco - Grecanico"),
        result(2025, "2025-10-01", 1.4, sample="Grecanico 25"),
        result(2026, "2026-10-01", 1.6, sample="Grecanico 2026"),
    ]

    projection = _project_lab_series(rows, 2026)[0]

    assert projection["sample_name"] == "Grecanico"
    assert projection["historical_vintage_count"] == 3
    assert projection["projected_endpoint"] == pytest.approx(1.6)


def test_documented_grenache_and_nerello_aliases_are_normalized() -> None:
    assert _canonical_sample_name("Granache 25") == "grenache"
    assert _canonical_sample_name("Grenache 2025") == "grenache"
    assert _canonical_sample_name("Nerello 25") == "nerello mascalese"
    assert _canonical_sample_name("Nerello Mascalese 2025") == "nerello mascalese"
    assert _canonical_sample_name("Narello Macalase 2025") == "nerello mascalese"
    assert _canonical_sample_name("Nerello Macalase") == "nerello mascalese"

    rows = [
        result(2025, "2025-10-01", 1.0, sample="Nerello Mascalese"),
        result(2026, "2026-10-01", 1.5, sample="Nerello"),
    ]
    projection = _project_lab_series(rows, 2026)[0]
    assert projection["sample_name"] == "Nerello Mascalese"
    assert projection["historical_vintage_count"] == 1
    assert projection["projected_endpoint"] == pytest.approx(1.5)


def test_durable_lab_learning_is_versioned_walk_forward_and_in_current_pipeline() -> None:
    root = Path(__file__).resolve().parents[1]
    migration = (root / "db/migrations/119_durable_laboratory_learning.sql").read_text(encoding="utf-8")
    laboratory_source = (root / "app/domains/laboratory.py").read_text(encoding="utf-8")
    routes = (root / "app/domains/laboratory_routes.py").read_text(encoding="utf-8")
    main = (root / "app/main.py").read_text(encoding="utf-8")
    mcp = (root / "app/mcp_server.py").read_text(encoding="utf-8")
    for field in ["source_sample_name", "canonical_sample_name", "lab_learning_cases", "lab_learning_outcomes", "lab_learning_models"]:
        assert field in migration
    assert "def normalize_historical_lab_samples" in laboratory_source
    assert "def refresh_lab_learning" in laboratory_source
    assert "future measurements are excluded from every prediction input" in laboratory_source
    assert '"learning_active_low_accuracy"' in laboratory_source
    assert "direction_accuracy >= 60" in laboratory_source
    assert "/api/v1/labs/learning-status" in routes
    assert "refresh_lab_learning(record_id)" in routes
    assert "refresh_lab_learning()" in main
    assert "refresh_treatment_weather_learning()" in main
    assert "refresh_lab_learning(sample_id)" in mcp


def test_walk_forward_direction_scoring_uses_only_cutoff_projection_and_later_actual() -> None:
    assert _direction_matches(1.0, 1.5, 1.4) is True
    assert _direction_matches(1.0, 0.8, 1.4) is False
    assert _direction_matches(1.0, 1.0, 1.0) is True


def test_variety_standards_show_only_recorded_markers_and_keep_missing_visible() -> None:
    series = _project_lab_series([
        result(2025, "2025-10-01", 1.5, sample="Nerello Mascalese", target_min=1.0, target_max=2.0),
        result(2026, "2026-10-01", 1.4, sample="Nerello", target_min=1.0, target_max=2.0),
        result(2026, "2026-10-01", 1.2, sample="Grecanico"),
    ], 2026)

    standards = _variety_lab_standards(series, [{"name": "Narello Macalase"}, {"name": "Grecanico"}])

    assert standards[0]["variety_name"] == "Nerello Mascalese"
    assert standards[0]["status"] == "recorded"
    assert standards[0]["standards"][0]["minimum"] == 1.0
    assert standards[0]["standards"][0]["maximum"] == 2.0
    assert standards[1]["status"] == "not_recorded"
    assert standards[1]["standards"] == []


def test_projection_is_unavailable_without_matching_history() -> None:
    projection = _project_lab_series([result(2026, "2026-10-01", 1.5)], 2026)[0]

    assert projection["projected_endpoint"] is None
    assert projection["confidence"] == "not_available"
    assert projection["historical_vintage_count"] == 0
    assert projection["ai_projection"]["value"] is None
    assert projection["ai_projection"]["method"] == "insufficient_measured_trajectory"


def test_ai_projection_uses_current_measured_slope_when_history_is_missing() -> None:
    rows = [
        result(2026, "2026-10-01", 1.0),
        result(2026, "2026-10-11", 2.0),
    ]

    projection = _project_lab_series(rows, 2026)[0]

    assert projection["projected_endpoint"] is None
    assert projection["ai_projection"]["method"] == "current_trajectory_14_day"
    assert projection["ai_projection"]["confidence"] == "low"
    assert projection["ai_projection"]["slope_per_day"] == pytest.approx(0.1)
    assert projection["ai_projection"]["value"] == pytest.approx(3.4)
    assert projection["ai_projection"]["date"] == "2026-10-25"


def test_ai_projection_prefers_exact_vintage_evidence() -> None:
    rows = [
        result(2025, "2025-10-01", 1.5),
        result(2026, "2026-10-01", 1.4),
        result(2026, "2026-10-11", 1.2),
    ]

    projection = _project_lab_series(rows, 2026)[0]

    assert projection["ai_projection"]["method"] == "like_for_like_vintage_model"
    assert projection["ai_projection"]["value"] == projection["projected_endpoint"]
    assert "not treated as a measurement" not in " ".join(projection["ai_projection"]["drivers"])


def test_lab_current_finding_uses_only_the_newest_report_date() -> None:
    old = result(2026, "2026-10-01", 1.0)
    newest = result(2026, "2026-10-11", 2.2, target_min=1.0, target_max=2.0)
    old.update({"sample_id": "old", "comparison_flag": "normal", "source_document": "old.pdf", "laboratory": "Test lab"})
    newest.update({"sample_id": "new", "comparison_flag": "high", "source_document": "new.pdf", "laboratory": "Test lab"})
    rows = [old, newest]
    series = _project_lab_series(rows, 2026)

    finding = _lab_current_finding(rows, series, 2026)

    assert finding["report_date"] == "2026-10-11"
    assert finding["source_documents"] == ["new.pdf"]
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["value"] == pytest.approx(2.2)
    assert "no cellar, harvest, or treatment action" in finding["decision_boundary"]


def test_projection_uses_vintage_instead_of_report_calendar_year() -> None:
    rows = [
        result(2024, "2025-01-09", 0.4),
        result(2025, "2026-01-09", 0.3),
    ]

    projection = _project_lab_series(rows, 2025)[0]

    assert projection["latest_date"] == "2026-01-09"
    assert projection["latest_value"] == pytest.approx(0.3)
    assert projection["historical_endpoint_average"] == pytest.approx(0.4)


def test_outlook_uses_latest_available_vintage_when_selected_year_has_no_results(monkeypatch) -> None:
    rows = [result(2024, "2024-10-01", 1.0), result(2025, "2025-10-01", 1.2)]
    for row in rows:
        row.update({"sample_id": row["result_id"], "authoritative_vintage_year": row["vintage_year"], "source_document": "lab.pdf", "laboratory": "Test lab"})
    monkeypatch.setattr(laboratory, "fetch_all", lambda *_args, **_kwargs: [dict(row) for row in rows])
    outlook = laboratory.vintage_outlook(2026)
    assert outlook["year"] == 2026
    assert outlook["analysis_year"] == 2025
    assert outlook["using_latest_available_vintage"] is True
    assert outlook["series"][0]["latest_value"] == pytest.approx(1.2)
    assert outlook["current_finding"]["status"] == "source_needed"


@pytest.mark.parametrize(
    ("current", "expected"),
    [(0.5, "below"), (1.5, "within"), (2.5, "above")],
)
def test_projection_compares_only_to_approved_target_range(current: float, expected: str) -> None:
    rows = [
        result(2025, "2025-10-01", 1.5, target_min=1.0, target_max=2.0),
        result(2026, "2026-10-01", current, target_min=1.0, target_max=2.0),
    ]

    assert _project_lab_series(rows, 2026)[0]["projected_status"] == expected
