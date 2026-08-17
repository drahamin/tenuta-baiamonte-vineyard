import pytest

from app.main import calculate_blend_program


def test_nerello_blend_uses_finished_blend_percentage() -> None:
    result = calculate_blend_program(2560, 470, 1833)

    assert result["required_grenache_kg"] == pytest.approx(177.968, abs=0.001)
    assert result["exact_grenache_crates"] == pytest.approx(11.865, abs=0.001)
    assert result["whole_grenache_crates"] == 12
    assert result["whole_crate_pick_kg"] == 180
    assert result["remaining_grenache_kg"] == pytest.approx(292.032, abs=0.001)
    assert result["wines"][0]["wine_l"] == pytest.approx(1916.578, abs=0.001)
    assert result["wines"][1]["wine_l"] == pytest.approx(1283.1, abs=0.001)
    assert result["wines"][2]["wine_l"] == pytest.approx(204.422, abs=0.001)


def test_blend_percentage_is_adjustable_for_live_scenarios() -> None:
    result = calculate_blend_program(2560, 470, 1833, grenache_pct=10)

    assert result["required_grenache_kg"] == pytest.approx(284.444, abs=0.001)
    assert result["whole_grenache_crates"] == 19
    assert result["remaining_grenache_kg"] == pytest.approx(185.556, abs=0.001)


def test_blend_program_reports_grenache_shortage() -> None:
    result = calculate_blend_program(2560, 100, 1833)

    assert result["grenache_shortage_kg"] == pytest.approx(77.968, abs=0.001)
    assert result["remaining_grenache_kg"] == 0


def test_blend_program_rejects_impossible_settings() -> None:
    with pytest.raises(ValueError):
        calculate_blend_program(100, 100, 100, grenache_pct=100)
