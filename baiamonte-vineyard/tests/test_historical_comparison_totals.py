from pathlib import Path
from tests.source_helpers import backend_source


ROOT = Path(__file__).resolve().parents[1]


def test_vintage_history_prefers_explicit_total_without_double_counting_components() -> None:
    source = backend_source(ROOT)

    assert "MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN grapes_kg END)" in source
    assert "SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN grapes_kg END)" in source
    assert "MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN wine_l END)" in source
    assert "SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN wine_l END)" in source
