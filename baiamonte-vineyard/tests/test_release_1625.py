from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/199_record_grecanico_winy_and_closed_top_racking.sql"


def test_release_version_is_11025():
    assert 'version: "1.10.27"' in (ROOT / "config.yaml").read_text()


def test_grecanico_winy_addition_is_exact_and_product_is_traceable():
    sql = MIGRATION.read_text()
    assert "w.code='GRC-2026-01-P'" in sql
    assert "'WINY','other','applied'" in sql
    assert "'2026-10-01 00:00:00',30.0000,'g'" in sql
    assert "E224 potassium metabisulfite" in sql
    assert "approximately 2.80 g/hL" in sql
    assert "actual free and total SO2 are not inferred" in sql


def test_closed_top_racking_preserves_unknown_vessel_facts():
    sql = MIGRATION.read_text()
    assert "'CT-GRC-P-2026'" in sql
    assert "it is not a claim about the vessel rated capacity" in sql
    assert "physical destination-vessel identity/rating" in sql
    assert "w.stage='aging',w.lot_status='active'" in sql
    assert "GRC-2026-01-P racked out to a closed-top container" in sql


def test_post_racking_pipeline_requests_only_decision_relevant_so2_tests():
    sql = MIGRATION.read_text()
    assert "JSON_ARRAY('ph','free_so2','total_so2')" in sql
    assert "do not treat the theoretical product conversion as a laboratory result" in sql
    assert "no further WINY dose is generated until these results are linked" in sql
