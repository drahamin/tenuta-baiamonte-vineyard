from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_matrix_contains_nine_exact_variety_year_dates() -> None:
    migration = (ROOT / "db/migrations/053_authoritative_harvest_dates_2023_2025.sql").read_text()
    expected = {
        (2023, "Grecanico", "2023-09-23"),
        (2023, "Grenache", "2023-09-24"),
        (2023, "Nerello Mascalese", "2023-10-08"),
        (2024, "Grecanico", "2024-09-11"),
        (2024, "Grenache", "2024-09-23"),
        (2024, "Nerello Mascalese", "2024-09-23"),
        (2025, "Grecanico", "2025-09-11"),
        (2025, "Grenache", "2025-09-17"),
        (2025, "Nerello Mascalese", "2025-09-23"),
    }
    for year, variety, pick_date in expected:
        assert f"{year},'{variety}','{pick_date}','{pick_date}','day','user_authoritative'" in migration


def test_conflicting_2023_grenache_claim_is_audited_not_trained() -> None:
    migration = (ROOT / "db/migrations/053_authoritative_harvest_dates_2023_2025.sql").read_text()
    assert "fact_date=NULL" in migration
    assert "date_precision='unknown'" in migration
    assert "evidence_status='superseded_date'" in migration
    assert "Earlier date discarded" in migration
    assert "canonical_table=NULL" in migration
