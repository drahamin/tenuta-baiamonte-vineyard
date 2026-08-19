from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_user_confirmed_2023_pick_and_crush_dates_are_separate() -> None:
    migration = (ROOT / "db/migrations/051_2023_exact_harvest_chronology.sql").read_text()
    assert "'Grecanico','2023-09-23','2023-09-24','day'" in migration
    assert "'Grenache','2023-09-24','2023-09-24','day'" in migration
    assert "'Nerello Mascalese','2023-10-08','2023-10-08','day'" in migration
    assert "'2023-grecanico-crush','2023-09-25'" in migration
    assert "'2023-grenache-crush','2023-10-13'" in migration
    assert "'2023-nerello-crush','2023-10-26'" in migration
    assert "harvest_date_precision=VALUES(harvest_date_precision)" in migration
