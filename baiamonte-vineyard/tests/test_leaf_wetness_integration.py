from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_managed_dashboards_surface_leaf_wetness_and_battery_health():
    overview = (ROOT / "dashboards" / "vineyard-overview.yaml").read_text(encoding="utf-8")
    ipad = (ROOT / "dashboards" / "ipad-panel.yaml").read_text(encoding="utf-8")

    for dashboard in (overview, ipad):
        assert "sensor.gw2000b_leaf_wetness_1" in dashboard
        assert "sensor.gw2000b_leaf_wetness_1_battery" in dashboard

    assert "title: Leaf Wetness" in overview
    assert "graph_span: 48h" in overview
    assert "max: 100" in overview
