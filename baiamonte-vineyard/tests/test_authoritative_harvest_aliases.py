from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_legacy_nerello_alias_receives_authoritative_metadata() -> None:
    migration = (ROOT / "db/migrations/054_normalize_authoritative_harvest_aliases.sql").read_text()
    assert "WHEN 2023 THEN '2023-10-08'" in migration
    assert "WHEN 2024 THEN '2024-09-23'" in migration
    assert "WHEN 2025 THEN '2025-09-23'" in migration
    assert "LOWER(TRIM(variety_name)) LIKE 'nerello%'" in migration
    assert "harvest_date_precision='day'" in migration
    assert "evidence_status='user_authoritative'" in migration
