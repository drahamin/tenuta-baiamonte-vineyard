"""Configurable moving cellar demonstration data for the dashboard and TV."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from .config import Settings, runtime_option


def demo_enabled(settings: Settings) -> bool:
    return str(runtime_option("cellar_mode", settings.cellar_mode)).strip().casefold() == "demo"


def _number(parts: list[str], index: int, fallback: float) -> float:
    try:
        return float(parts[index])
    except (IndexError, TypeError, ValueError):
        return fallback


def demo_cellar(settings: Settings, year: int) -> dict[str, Any]:
    """Return visibly active demo tanks using editable Home Assistant baselines."""
    raw = str(runtime_option("cellar_demo_tanks", settings.cellar_demo_tanks) or settings.cellar_demo_tanks)
    now = datetime.now(timezone.utc)
    phase = now.timestamp() / 90
    tanks: list[dict[str, Any]] = []
    for index, definition in enumerate(part.strip() for part in raw.split(",") if part.strip()):
        parts = [value.strip() for value in definition.split("|")]
        capacity = max(1, _number(parts, 1, 750))
        level_base = min(100, max(0, _number(parts, 4, 70)))
        level = min(100, max(0, level_base + math.sin(phase + index * 1.4) * 0.7))
        temp_base = _number(parts, 5, 20)
        density_base = _number(parts, 6, 1.020)
        brix_base = _number(parts, 7, 10)
        ph_base = _number(parts, 8, 3.35)
        tanks.append({
            "id": f"demo-{index + 1}",
            "code": f"D-{index + 1:02d}",
            "name": parts[0] if parts else f"Tank {index + 1}",
            "container_type": "barrel" if len(parts) > 3 and parts[3].casefold() == "aging" else "tank",
            "capacity_l": round(capacity, 1),
            "volume_l": round(capacity * level / 100, 1),
            "level_pct": round(level, 1),
            "stage": parts[3] if len(parts) > 3 and parts[3] else "fermentation",
            "variety_summary": parts[2] if len(parts) > 2 and parts[2] else "Demo lot",
            "status": "demo",
            "source": "Demo mode · configurable in Home Assistant",
            "temp_c": round(temp_base + math.sin(phase / 2 + index) * 0.25, 1),
            "density_sg": round(max(0.980, density_base - (math.sin(phase / 3 + index) + 1) * 0.0005), 3),
            "brix": round(max(0, brix_base - (math.sin(phase / 3 + index) + 1) * 0.08), 1),
            "ph": round(ph_base + math.sin(phase / 4 + index) * 0.01, 2),
            "sensor_entity_id": None,
            "reading_at": now.isoformat(),
            "next_check_at": (now + timedelta(hours=index + 1)).isoformat(),
        })
        if len(tanks) >= 8:
            break
    processes = [
        {
            "id": f"demo-process-{index + 1}",
            "observed_at": now.isoformat(),
            "vessel_name": tank["name"],
            "lot_name": tank["variety_summary"],
            "stage": tank["stage"],
            "temp_c": tank["temp_c"],
            "density_sg": tank["density_sg"],
            "brix": tank["brix"],
            "ph": tank["ph"],
            "cap_management": "Demo circulation running" if tank["stage"] == "fermentation" else None,
            "sensory_observation": "Demo readings updating",
            "next_check_at": tank["next_check_at"],
            "status": "demo",
        }
        for index, tank in enumerate(tanks[:4])
    ]
    return {"year": year, "demo": True, "tanks": tanks, "processes": processes, "updated_at": now.isoformat()}
