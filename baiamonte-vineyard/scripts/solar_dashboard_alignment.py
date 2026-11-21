"""Align solar cards in Baiamonte's existing storage-mode Lovelace dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path

from websockets.sync.client import connect

LOCAL = "sensor.baiamonte_growatt_local_solar_forecast"
OBSERVED = "sensor.baiamonte_growatt_solar_input_power"
SOLCAST = "sensor.solcast_pv_forecast_forecast_today"
VIEWS = {"default_view", "display-view-energy", "solar", "battery-bank", "power", "generator"}
LEGACY_CHARTS = {"Solar Forcast Vs. Input", "Solar forecast", "Actual and estimated solar production"}
ENTITIES = {
    "sensor.solcast_pv_forecast_power_now": (LOCAL + "_power_now", "Local forecast now"),
    SOLCAST: (LOCAL, "Local forecast today"),
    "sensor.solcast_pv_forecast_forecast_remaining_today": (LOCAL + "_remaining", "Local forecast remaining"),
    "sensor.solcast_pv_forecast_forecast_tomorrow": (LOCAL + "_tomorrow", "Local forecast tomorrow"),
    "sensor.solcast_pv_forecast_peak_forecast_today": (LOCAL + "_peak", "Local forecast peak"),
    "sensor.solcast_pv_forecast_peak_time_today": (LOCAL + "_peak_time", "Local forecast peak time"),
    "sensor.total_dc_input_power": (OBSERVED, "Solar input"),
    "sensor.daily_solar_power_in": ("sensor.baiamonte_growatt_solar_input_energy_today", "Recorded solar today"),
}


def _comparison_card(card: dict) -> dict:
    """Replace obsolete graph transforms with the current power series and units."""
    return {
        **{key: card[key] for key in ("grid_options", "section_mode", "view_layout", "visibility") if key in card},
        "type": "custom:apexcharts-card", "graph_span": "24h", "span": {"start": "day"},
        "header": {"show": True, "title": "Solar input and forecasts"},
        "series": [
            {"entity": OBSERVED, "name": "Solar input", "color": "#37b878", "unit": "W"},
            {"entity": LOCAL, "name": "Local forecast", "color": "#6da7d9", "unit": "W",
             "data_generator": (
                 "const day = moment(start).tz(hass.config.time_zone).format('YYYY-MM-DD');\n"
                 "if (entity.attributes.target_day !== day || entity.state === 'unavailable') return [];\n"
                 "return (entity.attributes.points || []).map(row => [Date.parse(row.observed_at), row.power_w]);"
             )},
            {"entity": SOLCAST, "name": "Solcast P50", "color": "#d9b735", "unit": "W",
             "data_generator": (
                 "const points = entity.attributes.detailedHourly || entity.attributes.detailedForecast || [];\n"
                 "return points.flatMap(row => {\n"
                 "  const time = Date.parse(row.period_start || row.datetime || row.time);\n"
                 "  const power = row.pv_estimate ?? row.estimate;\n"
                 "  return Number.isFinite(time) && power != null ? [[time, Number(power) * 1000]] : [];\n"
                 "});"
             )},
        ],
    }


def _align(value):
    if isinstance(value, list):
        return [_align(item) for item in value]
    if isinstance(value, str):
        return ENTITIES.get(value, (value,))[0]
    if not isinstance(value, dict):
        return value
    if value.get("type") == "custom:apexcharts-card":
        if (value.get("header") or {}).get("title") in LEGACY_CHARTS:
            return _comparison_card(value)
        return value
    title = str(value.get("title") or "")
    if title in {"Solcast Health", "Forecast Sites", "Solcast comparison"}:
        return value
    updated = {key: _align(item) for key, item in value.items()}
    entity = value.get("entity")
    if isinstance(entity, str) and entity in ENTITIES and value.get("name"):
        updated["name"] = ENTITIES[entity][1]
    return updated


def align_storage_dashboard(config: dict) -> dict:
    views = config.get("views", [])
    if not {"solar", "display-view-energy"} <= {view.get("path") for view in views}:
        return config
    return {
        **config,
        "views": [
            {**view, **{key: _align(view[key]) for key in ("cards", "sections", "badges") if key in view}}
            if view.get("path") in VIEWS else view
            for view in views
        ],
    }


def deploy_storage_solar_alignment(backup_root: Path) -> None:
    """Apply the narrow migration once via Home Assistant's authenticated API."""
    marker = backup_root / "storage-solar-alignment-v1.done"
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if marker.exists() or not token:
        return
    try:
        with connect("ws://supervisor/core/websocket", open_timeout=5, close_timeout=1, max_size=8 * 1024 * 1024) as socket:
            json.loads(socket.recv(timeout=5))
            socket.send(json.dumps({"type": "auth", "access_token": token}))
            if json.loads(socket.recv(timeout=5)).get("type") != "auth_ok":
                raise RuntimeError("Home Assistant rejected dashboard authentication")
            socket.send(json.dumps({"id": 1, "type": "lovelace/config", "url_path": "lovelace"}))
            result = json.loads(socket.recv(timeout=5))
            original = result.get("result")
            if not result.get("success") or not isinstance(original, dict):
                print("Solar dashboard alignment: legacy storage dashboard unavailable.", flush=True)
                return
            updated = align_storage_dashboard(original)
            if original != updated:
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / "lovelace-before-solar-alignment.json"
                if not backup.exists():
                    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump(original, stream)
                socket.send(json.dumps({"id": 2, "type": "lovelace/config/save", "url_path": "lovelace", "config": updated}))
                if not json.loads(socket.recv(timeout=8)).get("success"):
                    raise RuntimeError("Home Assistant rejected the aligned dashboard")
                print("Solar dashboard alignment: updated the existing storage-mode solar cards.", flush=True)
            backup_root.mkdir(parents=True, exist_ok=True)
            marker.touch()
    except Exception as exc:
        print(f"Solar dashboard alignment: {type(exc).__name__}.", flush=True)
