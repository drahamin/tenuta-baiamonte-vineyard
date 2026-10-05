from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_purchased_grenache_intake_is_traceable_and_transparent():
    sql = (ROOT / "db/migrations/202_record_purchased_grenache_cold_hold.sql").read_text()

    assert "2026-GRN-PUR-01" in sql
    assert "GRN-2026-02" in sql
    assert "T-GRN-PUR-1000" in sql
    assert "1078.000" in sql
    assert "manual_temp_c" in sql and "6.000" in sql
    assert "must_wine_l remains NULL" in sql
    assert "Tannin — exact product pending" in sql
    assert "Sulfur — exact product pending" in sql
    assert "2026-10-06" in sql


def test_release_version_1_10_32():
    assert 'version: "1.10.33"' in (ROOT / "config.yaml").read_text()
