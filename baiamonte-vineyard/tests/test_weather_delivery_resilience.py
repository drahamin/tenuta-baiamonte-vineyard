from __future__ import annotations

from pathlib import Path

from app import display_data


class DeferredThread:
    instances: list["DeferredThread"] = []

    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        self.started = True


def reset_weather_state(monkeypatch) -> None:
    DeferredThread.instances = []
    monkeypatch.setattr(display_data, "_weather_cache", None)
    monkeypatch.setattr(display_data, "_weather_refreshing", False)
    monkeypatch.setattr(display_data, "_weather_last_refresh_attempt", 0.0)
    monkeypatch.setattr(display_data, "_ha_cache", None)
    monkeypatch.setattr(display_data.threading, "Thread", DeferredThread)


def test_cold_weather_request_returns_recorded_conditions_before_ha_refresh(monkeypatch):
    reset_weather_state(monkeypatch)
    monkeypatch.setattr(display_data, "estate_id", lambda: "estate-1")
    monkeypatch.setattr(
        display_data,
        "fetch_one",
        lambda *_args, **_kwargs: {
            "observed_at": "2026-10-26 08:15:00",
            "temp_c": 14.2,
            "humidity_pct": 88,
            "rain_rate_mm_h": 0,
        },
    )
    monkeypatch.setattr(
        display_data,
        "_load_home_assistant_display_data",
        lambda: (_ for _ in ()).throw(AssertionError("HA refresh must not run in the request")),
    )

    payload = display_data.weather_context_payload()

    assert payload["current"]["temp_c"] == 14.2
    assert payload["current"]["raining_now"] is False
    assert payload["source"] == "database_last_known"
    assert payload["cache"]["status"] == "last_known"
    assert payload["cache"]["refresh_pending"] is True
    assert len(DeferredThread.instances) == 1
    assert DeferredThread.instances[0].started is True


def test_weather_refresh_is_single_flight(monkeypatch):
    reset_weather_state(monkeypatch)

    assert display_data._schedule_weather_refresh() is True
    assert display_data._schedule_weather_refresh() is False
    assert len(DeferredThread.instances) == 1


def test_successful_background_refresh_replaces_last_known_conditions(monkeypatch):
    reset_weather_state(monkeypatch)
    display_data._store_weather_cache(
        {"available": True, "current": {"temp_c": 12}, "forecast": [], "advisories": []},
        "database_last_known",
    )
    monkeypatch.setattr(
        display_data,
        "_load_home_assistant_display_data",
        lambda: {
            "available": True,
            "live_weather": {"observed_at": "2026-10-26T09:00:00+01:00", "temp_c": 15},
            "weather_forecast": [{"datetime": "2026-10-27", "condition": "sunny"}],
            "weather_forecast_entity": "weather.baiamonte",
            "weather_station_capabilities": {"forecast_entity_available": True},
        },
    )

    display_data._refresh_weather_cache()
    payload = display_data._weather_cache_response(display_data._weather_cache_snapshot())

    assert payload["source"] == "home_assistant"
    assert payload["cache"]["status"] == "fresh"
    assert payload["current"]["temp_c"] == 15
    assert payload["forecast_entity"] == "weather.baiamonte"


def test_failed_background_refresh_keeps_last_complete_snapshot(monkeypatch):
    reset_weather_state(monkeypatch)
    original = display_data._store_weather_cache(
        {"available": True, "current": {"temp_c": 13}, "forecast": [], "advisories": []},
        "home_assistant",
    )
    monkeypatch.setattr(display_data, "_load_home_assistant_display_data", lambda: {"available": False})

    display_data._refresh_weather_cache()

    assert display_data._weather_cache_snapshot() == original
    assert display_data._weather_refreshing is False


def test_weather_network_calls_have_short_bounded_timeouts():
    source = (display_data.__file__ and open(display_data.__file__, encoding="utf-8").read())

    assert source.count("urlopen(request, timeout=1.5)") >= 2
    assert "threading.Thread(target=_refresh_weather_cache" in source


def test_weather_renderer_uses_defined_source_context_before_rendering_shared_pages():
    source = Path(display_data.__file__).resolve().parent / "static" / "app.js"
    renderer = source.read_text(encoding="utf-8").split("function renderWeather(){", 1)[1].split("function drawChart", 1)[0]

    assert "weatherStatus(state.weatherCurrent,freshness)" in renderer
    assert "sourceLabel" not in renderer
    assert "weatherCache.refresh_pending" not in renderer

