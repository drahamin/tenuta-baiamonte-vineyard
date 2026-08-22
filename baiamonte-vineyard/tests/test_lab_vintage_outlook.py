from __future__ import annotations

import pytest

from app.domains.laboratory import _canonical_sample_name, _project_lab_series


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

    rows = [
        result(2025, "2025-10-01", 1.0, sample="Nerello Mascalese"),
        result(2026, "2026-10-01", 1.5, sample="Nerello"),
    ]
    projection = _project_lab_series(rows, 2026)[0]
    assert projection["sample_name"] == "Nerello Mascalese"
    assert projection["historical_vintage_count"] == 1
    assert projection["projected_endpoint"] == pytest.approx(1.5)


def test_projection_is_unavailable_without_matching_history() -> None:
    projection = _project_lab_series([result(2026, "2026-10-01", 1.5)], 2026)[0]

    assert projection["projected_endpoint"] is None
    assert projection["confidence"] == "not_available"
    assert projection["historical_vintage_count"] == 0


def test_projection_uses_vintage_instead_of_report_calendar_year() -> None:
    rows = [
        result(2024, "2025-01-09", 0.4),
        result(2025, "2026-01-09", 0.3),
    ]

    projection = _project_lab_series(rows, 2025)[0]

    assert projection["latest_date"] == "2026-01-09"
    assert projection["latest_value"] == pytest.approx(0.3)
    assert projection["historical_endpoint_average"] == pytest.approx(0.4)


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
