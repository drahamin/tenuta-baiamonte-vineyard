"""Native solar forecast platform. Adapt watts over each hour to watt-hours."""

from datetime import datetime, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo

FORECAST_SENSOR = "sensor.baiamonte_growatt_local_solar_forecast"
ROME = ZoneInfo("Europe/Rome")


def hourly_wh(attributes, now=None):
    today = (now or datetime.now(timezone.utc)).astimezone(ROME).date()
    allowed = {today, today + timedelta(days=1)}
    result = {}
    for forecast in (attributes, attributes.get("tomorrow") or {}):
        for point in forecast.get("points", []):
            try:
                stamp = datetime.fromisoformat(point["observed_at"])
                power = float(point["power_w"])
            except (KeyError, TypeError, ValueError):
                continue
            if (stamp.tzinfo and stamp.astimezone(ROME).date() in allowed
                    and forecast.get("target_day") == stamp.astimezone(ROME).date().isoformat()
                    and isfinite(power) and power >= 0):
                result[stamp.isoformat()] = power
    return result


async def async_get_solar_forecast(hass, config_entry_id):
    entry = hass.config_entries.async_get_entry(config_entry_id)
    state = hass.states.get(FORECAST_SENSOR)
    if entry is None or state is None:
        return None
    values = hourly_wh(state.attributes)
    return {"wh_hours": values} if values else None
