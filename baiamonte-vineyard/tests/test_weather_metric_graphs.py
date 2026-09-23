from pathlib import Path

from app import main


ROOT = Path(__file__).resolve().parents[1]


def test_weather_history_returns_recent_observations_in_chronological_order(monkeypatch):
    captured = {}

    def fake_fetch_all(query, params):
        captured["query"] = query
        captured["params"] = params
        return [
            {"observed_at": "2026-09-23 12:10:00", "leaf_wetness_pct": 13},
            {"observed_at": "2026-09-23 12:00:00", "leaf_wetness_pct": 11},
        ]

    monkeypatch.setattr(main, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(main, "estate_id", lambda: "estate-1")

    payload = main.weather_history(48)

    assert payload["hours"] == 48
    assert [row["leaf_wetness_pct"] for row in payload["observations"]] == [11, 13]
    assert "FROM weather_observations" in captured["query"]
    assert "ORDER BY observed_at DESC LIMIT 3000" in captured["query"]
    assert captured["params"] == ("estate-1", 48)


def test_weather_cards_open_accessible_measured_history_graphs():
    html = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/weather-metrics.js").read_text()
    styles = (ROOT / "app/static/app.css").read_text()

    assert 'id="weatherMetricDialog"' in html
    assert 'data-weather-hours="24"' in html
    assert 'data-weather-hours="168"' in html
    assert 'src="assets/assets/weather-metrics.js' in html
    for metric in ("Temperature", "Humidity", "Pressure", "Solar", "Leaf wetness", "VPD"):
        assert f"'{metric}':" in script
    assert "api/v1/weather/history?hours=" in script
    assert "role','button'" in script
    assert "Gaps remain gaps" in html
    assert ".weather-stat-clickable" in styles
    assert ".weather-metric-summary" in styles
    assert ".weather-metric-message[hidden]" in styles
