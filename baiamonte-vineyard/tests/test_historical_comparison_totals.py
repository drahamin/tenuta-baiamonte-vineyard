from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vintage_history_prefers_explicit_total_without_double_counting_components() -> None:
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

    assert "MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN grapes_kg END)" in source
    assert "SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN grapes_kg END)" in source
    assert "MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN wine_l END)" in source
    assert "SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN wine_l END)" in source
