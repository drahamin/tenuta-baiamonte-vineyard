from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_2023_grenache_early_lot_preserves_later_pick_and_press_uncertainty() -> None:
    migration = (ROOT / "db/migrations/052_expand_exact_harvest_training.sql").read_text()
    assert "first_pick_date='2023-09-17'" in migration
    assert "last_pick_date='2023-09-24'" in migration
    assert "20,'crates'" in migration
    assert "6,'h'" in migration
    assert "50-70 bar" in migration
    assert "120 bar" in migration
    assert "not promoted to an exact inventory balance" in migration


def test_all_three_2025_variety_dates_are_exact_training_evidence() -> None:
    migration = (ROOT / "db/migrations/052_expand_exact_harvest_training.sql").read_text()
    assert "2025,'Grecanico','2025-09-11','2025-09-11','day'" in migration
    assert "2025,'Grenache','2025-09-17','2025-09-17','day'" in migration
    assert "2025,'Nerello Mascalese','2025-09-23','2025-09-23','day'" in migration
