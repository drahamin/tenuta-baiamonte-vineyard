from pathlib import Path

import pytest

from app.domains.harvest import calculate_varietal_program


ROOT = Path(__file__).resolve().parents[1]


def test_varieties_are_calculated_as_independent_wines() -> None:
    result = calculate_varietal_program(2560, 470, 1833)

    assert result["vinification_policy"] == "separate_varietals"
    assert [wine["finished_wine"] for wine in result["wines"]] == ["Nerello Mascalese", "Grecanico", "Grenache"]
    assert [wine["composition"] for wine in result["wines"]] == ["100% Nerello Mascalese", "100% Grecanico", "100% Grenache"]
    assert sum(wine["grape_kg"] for wine in result["wines"]) == 4863
    assert result["wines"][0]["crates"] == 171
    assert result["wines"][2]["crates"] == 32


def test_varietal_program_validates_operational_settings() -> None:
    with pytest.raises(ValueError):
        calculate_varietal_program(100, 100, 100, tank_working_fill_pct=101)


def test_active_system_contains_no_cross_variety_crate_calculator() -> None:
    active = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (ROOT / "app", ROOT / "scripts")
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".js", ".html"}
    ).lower()
    assert "grenache_pct" not in active
    assert "blend_crate_calculator" not in active
    assert "/api/v1/agronomy/blend-program" not in active


def test_retirement_migration_preserves_real_three_lot_cellar() -> None:
    migration = (ROOT / "db/migrations/156_separate_varietal_vinification.sql").read_text(encoding="utf-8")
    assert "GRC-2026-01-P" in migration
    assert "GRC-2026-01-T" in migration
    assert "GRN-2026-01" in migration
    assert "2026-GRC-C01" in migration
    assert "2026-NM-C01" in migration
    assert "excluded_obsolete_planning_lot" in migration
    assert "manual_volume_l=450.000" in migration
    assert "not pressed juice" in migration
