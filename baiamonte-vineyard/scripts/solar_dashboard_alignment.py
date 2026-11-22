"""Align solar cards in Baiamonte's existing storage-mode Lovelace dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from websockets.sync.client import connect

from app.ha_auth import home_assistant_token

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


def _align_garage_cards(value):
    if isinstance(value, list):
        return [_align_garage_cards(item) for item in value]
    if not isinstance(value, dict):
        return value
    location_bindings = {
        "Back Driveway Mid": ("camera.topvineyard", "camera.rear_gate_360"),
        "Backyard": ("camera.rear_gate_360", "camera.topvineyard"),
        "Inside Front Gate": ("camera.front_gate", "camera.front_yard"),
        "Front Yard": ("camera.front_yard", "camera.front_gate"),
    }
    binding = location_bindings.get(value.get("title"))
    if value.get("type") == "picture-glance" and binding and value.get("camera_image") == binding[0]:
        return {**value, "camera_image": binding[1]}
    if (
        value.get("type") == "picture-glance"
        and value.get("title") == "Garage"
        and value.get("camera_image") == "camera.indoor_cam"
    ):
        return {**value, "camera_image": "camera.garage"}
    return {key: _align_garage_cards(item) for key, item in value.items()}


def align_storage_garage_dashboard(config: dict) -> dict:
    if not any(view.get("path") == "new-cameras" for view in config.get("views", [])):
        return config
    return {
        **config,
        "views": [
            _align_garage_cards(view) if view.get("path") == "new-cameras" else view
            for view in config["views"]
        ],
    }


def deploy_storage_solar_alignment(backup_root: Path) -> None:
    _deploy_storage_alignment(backup_root, "solar", align_storage_dashboard)


def deploy_storage_camera_location_alignment(backup_root: Path) -> None:
    _deploy_storage_alignment(backup_root, "camera-locations", align_storage_garage_dashboard)


def deploy_storage_garage_alignment(backup_root: Path) -> None:
    _deploy_storage_alignment(backup_root, "garage", align_storage_garage_dashboard)


def _deploy_storage_alignment(backup_root: Path, subject: str, align: Callable[[dict], dict]) -> None:
    """Apply the narrow migration once via Home Assistant's authenticated API."""
    marker = backup_root / f"storage-{subject}-alignment-v1.done"
    if marker.exists():
        return
    label = f"{subject.capitalize()} dashboard alignment"
    token = home_assistant_token()
    if not token:
        print(f"{label}: Home Assistant authentication unavailable.", flush=True)
        return
    try:
        with connect("ws://supervisor/core/websocket", open_timeout=5, close_timeout=1, max_size=8 * 1024 * 1024) as socket:
            json.loads(socket.recv(timeout=5))
            socket.send(json.dumps({"type": "auth", "access_token": token}))
            if json.loads(socket.recv(timeout=5)).get("type") != "auth_ok":
                print(f"{label}: Home Assistant rejected authentication.", flush=True)
                return
            socket.send(json.dumps({"id": 1, "type": "lovelace/config", "url_path": "lovelace"}))
            result = json.loads(socket.recv(timeout=5))
            original = result.get("result")
            if not result.get("success") or not isinstance(original, dict):
                print(f"{label}: legacy storage dashboard unavailable.", flush=True)
                return
            updated = align(original)
            if original != updated:
                backup_root.mkdir(parents=True, exist_ok=True)
                backup = backup_root / f"lovelace-before-{subject}-alignment.json"
                if not backup.exists():
                    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, "w") as stream:
                        json.dump(original, stream)
                socket.send(json.dumps({"id": 2, "type": "lovelace/config/save", "url_path": "lovelace", "config": updated}))
                saved = json.loads(socket.recv(timeout=8))
                if not saved.get("success"):
                    code = (saved.get("error") or {}).get("code", "unknown")
                    print(f"{label}: dashboard save rejected ({code}).", flush=True)
                    return
                print(f"{label}: updated the existing storage-mode dashboard cards.", flush=True)
            backup_root.mkdir(parents=True, exist_ok=True)
            marker.touch()
    except Exception as exc:
        print(f"{label}: {type(exc).__name__}.", flush=True)
