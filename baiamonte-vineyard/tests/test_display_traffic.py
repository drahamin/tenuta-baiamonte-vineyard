from app.display_server import _scope_ais_payload, _traffic_map_reconnect


def test_ais_tv_payload_keeps_local_targets_without_upstream_history() -> None:
    payload = {
        "connection": "Connected",
        "generated_at": "2026-08-31T12:00:00Z",
        "last_error": None,
        "config": {
            "timeout_minutes": 30,
            "bounds": {"south": 36.0, "north": 39.0, "west": 12.0, "east": 17.0},
            "map_areas": [
                {"id": "baiamonte", "bounds": {"south": 37.0, "north": 38.0, "west": 14.0, "east": 16.0}}
            ],
        },
        "vessels": [
            {"mmsi": "1", "latitude": 37.5, "longitude": 15.0, "distance_km": 10},
            {"mmsi": "2", "latitude": 40.0, "longitude": 15.0, "distance_km": 5},
        ],
        "receiver_history": [{"large": "unused"}],
        "raw_messages": ["unused"],
    }

    result = _scope_ais_payload(payload)

    assert [row["mmsi"] for row in result["vessels"]] == ["1"]
    assert result["config"]["area_id"] == "baiamonte"
    assert "receiver_history" not in result
    assert "raw_messages" not in result


def test_transient_traffic_map_failure_renders_tv_reconnect_page() -> None:
    response = _traffic_map_reconnect("adsb")
    document = response.body.decode("utf-8")

    assert response.status_code == 200
    assert response.headers["x-baiamonte-traffic"] == "reconnecting"
    assert "ADS-B aircraft map reconnecting" in document
    assert "setTimeout(()=>location.reload(),15000)" in document
    assert '"detail"' not in document


def test_weather_map_reconnect_page_is_named_for_weather() -> None:
    document = _traffic_map_reconnect("adsb", weather=True).body.decode("utf-8")

    assert "Weather map reconnecting" in document
