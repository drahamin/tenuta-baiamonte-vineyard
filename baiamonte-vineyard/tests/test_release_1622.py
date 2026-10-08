from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/197_reconcile_wendy_current_harvest_notes.sql"


def test_release_version_is_11025():
    assert 'version: "1.10.36"' in (ROOT / "config.yaml").read_text()


def test_nerello_evening_sugar_addition_is_exact_and_requires_retest():
    sql = (ROOT / "db/migrations/198_record_nerello_evening_sugar_addition.sql").read_text()
    assert "w.code='NM-2026-01'" in sql
    assert "'crystalMUSTGRAPE','other','applied'" in sql
    assert "'2026-09-30 19:00:00',10.5000,'kg'" in sql
    assert "Retest potential alcohol after complete homogenization" in sql
    assert "does not by itself authorize another nutrient dose" in sql
    assert "Remaining cellar stock is not inferred" in sql


def test_wendy_current_grecanico_corrections_and_series_are_exact():
    sql = MIGRATION.read_text()
    assert "f.babo=16.8,f.temp_c=15" in sql
    assert "f.babo=16.0,f.temp_c=15" in sql
    assert "f.babo=12.2,f.temp_c=22" in sql
    assert "'wendy-current-grc-p-0926'" in sql
    assert "'T-03',18,0" in sql
    assert 'Babo was "almost 0"' in sql
    assert "Qualitative Babo is retained in text, not converted" in sql


def test_wendy_current_operations_preserve_unknowns_and_owner_unit_corrections():
    sql = MIGRATION.read_text()
    assert "CLARIL AF 60 g (not mg)" in sql
    assert "NUTRIFERM AROM PLUS 30 g/hL (not g/kg)" in sql
    assert "'source units/demijohn'" in sql
    assert "'Sulfur addition — exact product pending','other','applied'" in sql
    assert "do not calculate a dose or total mass" in sql
    assert "Babo and temperature were blank and remain unrecorded" in sql
    assert "o.operation_at='2026-09-16 16:50:00'" in sql
    assert "o.operation_type='Crush and press completed'" in sql


def test_wendy_current_nerello_pipeline_and_live_tank_profile_are_current():
    sql = MIGRATION.read_text()
    assert "'wendy-current-nm-0930-evening'" in sql
    assert "'2026-09-30 19:00:00',19,6.9" in sql
    assert "cp.manual_temp_c=19,cp.manual_babo=6.9" in sql
    assert "w.code='NM-2026-01'" in sql
    assert "'Pump-over'" in sql


def test_blank_grenache_actions_and_unresolved_lab_scope_are_not_invented():
    sql = MIGRATION.read_text()
    assert "'wendy-current-grenache-0913-1230'" in sql
    assert "Babo was explicitly not required per SV" in sql
    assert "'wendy-current-grenache-0913-evening'" in sql
    assert "Test each for volatile acidity and Brettanomyces" in sql
    assert "Do not assign this request to a wine lot" in sql


def test_wendy_current_nerello_labor_uses_net_weight_without_inferred_hours():
    sql = MIGRATION.read_text()
    assert "'Harvest crew (16 people)','Harvest',2139.60" in sql
    assert "'Cellar crew at Raiti (4 people)','Cellar processing',2139.60" in sql
    assert "Breaks, individual names and payable hours were not supplied" in sql
