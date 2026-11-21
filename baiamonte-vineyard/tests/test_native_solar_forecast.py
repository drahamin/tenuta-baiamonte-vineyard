import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def test_energy_uses_hourly_estimates_for_current_and_next_estate_dates():
    path = Path(__file__).resolve().parents[1] / "custom_components/baiamonte_solar_forecast/energy.py"
    spec = importlib.util.spec_from_file_location("native_solar_energy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.hourly_wh({
        "target_day": "2026-11-22",
        "points": [
            {"observed_at": "2026-11-22T13:00:00+01:00", "power_w": 1234},
            {"observed_at": "2026-11-22T15:00:00+01:00", "power_w": "unavailable"},
            {"observed_at": "2026-11-21T16:00:00+01:00", "power_w": 999},
        ],
        "tomorrow": {
            "target_day": "2026-11-23",
            "points": [{"observed_at": "2026-11-23T13:00:00+01:00", "power_w": 1330}],
        },
    }, now=datetime(2026, 11, 21, 23, 30, tzinfo=timezone.utc))
    assert result == {
        "2026-11-22T13:00:00+01:00": 1234,
        "2026-11-23T13:00:00+01:00": 1330,
    }
