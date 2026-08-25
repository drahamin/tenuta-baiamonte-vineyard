"""Database-backed controls for the vineyard's continuously running processes."""

from __future__ import annotations

import json
from typing import Any

from .config import get_settings
from .db import fetch_one, transaction
from .service import estate_id


PROCESS_ORDER = ("full_refresh", "weather", "forecast_sources", "product_catalog", "harvest", "planning", "cistern", "cameras", "gmail", "whatsapp", "finance", "etna", "traffic", "disease", "alerts", "public_feed")
PROCESS_MINUTES = {"full_refresh": 5, "planning": 5, "weather": 1, "forecast_sources": 30, "product_catalog": 1440, "harvest": 15, "cistern": 15, "cameras": 2, "gmail": 1, "whatsapp": 5, "finance": 15, "etna": 2, "traffic": 2, "disease": 5, "alerts": 2, "public_feed": 1}
PROCESS_MAX_MINUTES = {"disease": 30}
PROCESS_MAX_MINUTES["product_catalog"] = 43200
PROCESS_LABELS = {
    "full_refresh": "Complete system refresh",
    "planning": "Baiamonte Calendar & Tasks",
    "weather": "GW2000 weather & history",
    "forecast_sources": "External forecast evidence",
    "product_catalog": "Italian Ministry product catalog",
    "harvest": "Harvest readiness & projections",
    "cistern": "Cistern camera level",
    "cameras": "Estate camera awareness",
    "gmail": "Gmail intake",
    "whatsapp": "WhatsApp connection & catalogs",
    "finance": "Fatture in Cloud",
    "etna": "Mount Etna monitor",
    "public_feed": "Public harvest website",
    "traffic": "AIS & ADS-B summary",
    "disease": "Disease & stress model",
    "alerts": "Operational alerts",
}
PROCESS_CATEGORIES = {
    "full_refresh": "System",
    "planning": "Sources", "weather": "Sources", "forecast_sources": "Sources", "product_catalog": "Sources", "cistern": "Sources", "cameras": "Sources", "gmail": "Sources", "whatsapp": "Sources", "finance": "Sources", "etna": "Sources", "traffic": "Sources",
    "harvest": "Intelligence", "disease": "Intelligence", "alerts": "Intelligence", "public_feed": "Publishing",
}
PROCESS_DESCRIPTIONS = {
    "full_refresh": "Recovers sources that are missing or more than twice past their normal cadence; the manual run still refreshes every configured subsystem.",
    "planning": "Mirrors the shared Baiamonte Google Calendar and Tasks into MariaDB without creating duplicates.",
    "weather": "Imports live on-site GW2000 readings, replays Recorder history, then after a 48-hour grace period fills only persistent missing days from a labelled historical archive.",
    "forecast_sources": "Refreshes free, credential-free ensemble uncertainty, SIAS validation metadata, Sentinel-2 vegetation readiness and ECMWF seasonal planning context. Each source has a restricted model role.",
    "product_catalog": "Refreshes official Italian Ministry product identity and administrative status, then overlays exact or reviewable matches on Baiamonte products. Crop, target, rate and mixture approval remain separate.",
    "harvest": "Recalculates provisional harvest dates from weather/GDD, fruit and lab readiness, field reports, work, treatment and cellar constraints, with an optional guarded AI review.",
    "cistern": "Captures one private camera estimate and publishes the confirmed level.",
    "cameras": "Persists Eufy edge events, evaluates durable camera health and refreshes one oldest still per run with failure backoff to protect camera resources.",
    "gmail": "Reads allowed vineyard senders and queues new mail or attachments for review.",
    "whatsapp": "Refreshes sender health, the selected account's templates, groups, safe devices and approved camera inventory.",
    "finance": "Pulls read-only accounting documents and status from Fatture in Cloud.",
    "etna": "Refreshes official Etna, seismic, ash and aviation context.",
    "traffic": "Refreshes the local AIS and ADS-B summaries used by dashboards.",
    "disease": "Updates current and rolling disease and heat-stress decision support.",
    "alerts": "Evaluates overdue work, weather, lab, cellar and system warnings.",
    "public_feed": "Publishes the approved public harvest dates to the website.",
}


def _defaults() -> dict[str, Any]:
    settings = get_settings()
    return {
        "paused": False,
        "processes": {
            "full_refresh": {"enabled": True, "interval_minutes": max(PROCESS_MINUTES["full_refresh"], settings.full_refresh_minutes)},
            "planning": {"enabled": True, "interval_minutes": max(PROCESS_MINUTES["planning"], settings.planning_sync_minutes)},
            "weather": {"enabled": True, "interval_minutes": max(PROCESS_MINUTES["weather"], settings.weather_sync_minutes)},
            "forecast_sources": {"enabled": True, "interval_minutes": max(PROCESS_MINUTES["forecast_sources"], getattr(settings, "prediction_sources_minutes", 180))},
            "product_catalog": {"enabled": True, "interval_minutes": 10080},
            "harvest": {"enabled": True, "interval_minutes": 30},
            "cistern": {"enabled": bool(settings.cistern_level_ai_enabled), "interval_minutes": max(PROCESS_MINUTES["cistern"], settings.full_refresh_minutes)},
            "cameras": {"enabled": True, "interval_minutes": PROCESS_MINUTES["cameras"]},
            "gmail": {"enabled": bool(settings.gmail_address and settings.gmail_app_password), "interval_minutes": max(PROCESS_MINUTES["gmail"], settings.gmail_poll_minutes)},
            "whatsapp": {"enabled": bool((settings.whatsapp_access_token or settings.whatsapp_test_access_token) and (settings.whatsapp_phone_number_id or settings.whatsapp_test_phone_number_id)), "interval_minutes": 15},
            "finance": {"enabled": bool(settings.fattureincloud_token and settings.fattureincloud_company_id), "interval_minutes": max(PROCESS_MINUTES["finance"], settings.fattureincloud_sync_minutes)},
            "etna": {"enabled": bool(settings.etna_enabled), "interval_minutes": max(PROCESS_MINUTES["etna"], settings.etna_refresh_minutes)},
            "public_feed": {"enabled": bool(settings.public_publish_url), "interval_minutes": max(PROCESS_MINUTES["public_feed"], settings.public_publish_minutes)},
            "traffic": {"enabled": True, "interval_minutes": 5},
            "disease": {"enabled": True, "interval_minutes": 5},
            "alerts": {"enabled": True, "interval_minutes": 5},
        },
    }


def process_controls() -> dict[str, Any]:
    controls = _defaults()
    row = fetch_one("SELECT setting_value,updated_at FROM app_settings WHERE estate_id=%s AND setting_key='process_controls'", (estate_id(),))
    try:
        saved = json.loads(row["setting_value"]) if row and isinstance(row.get("setting_value"), str) else (row or {}).get("setting_value") or {}
    except (TypeError, ValueError):
        saved = {}
    controls["paused"] = bool(saved.get("paused", controls["paused"]))
    controls["updated_by"] = saved.get("updated_by")
    controls["updated_at"] = row.get("updated_at") if row else None
    for code in PROCESS_ORDER:
        configured = (saved.get("processes") or {}).get(code) or {}
        current = controls["processes"][code]
        current["enabled"] = bool(configured.get("enabled", current["enabled"]))
        try:
            current["interval_minutes"] = min(PROCESS_MAX_MINUTES.get(code, 1440), max(PROCESS_MINUTES[code], int(configured.get("interval_minutes", current["interval_minutes"]))))
        except (TypeError, ValueError):
            pass
        current["label"] = PROCESS_LABELS[code]
        current["category"] = PROCESS_CATEGORIES[code]
        current["description"] = PROCESS_DESCRIPTIONS[code]
        current["minimum_minutes"] = PROCESS_MINUTES[code]
    return controls


def save_process_controls(payload: dict[str, Any], updated_by: str) -> dict[str, Any]:
    current = process_controls()
    if "paused" in payload:
        current["paused"] = bool(payload["paused"])
    requested = payload.get("processes") or {}
    for code, values in requested.items():
        if code not in current["processes"] or not isinstance(values, dict):
            continue
        if "enabled" in values:
            current["processes"][code]["enabled"] = bool(values["enabled"])
        if "interval_minutes" in values:
            try:
                current["processes"][code]["interval_minutes"] = min(PROCESS_MAX_MINUTES.get(code, 1440), max(PROCESS_MINUTES[code], int(values["interval_minutes"])))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid interval for {code}")
    stored = {
        "paused": current["paused"],
        "processes": {code: {"enabled": item["enabled"], "interval_minutes": item["interval_minutes"]} for code, item in current["processes"].items()},
        "updated_by": updated_by,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'process_controls',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload) "
            "VALUES (%s,'operations-control','internal','schedule_updated','processed',%s)",
            (estate_id(), json.dumps(stored)),
        )
    return process_controls()
