from __future__ import annotations

import base64
import asyncio
import hashlib
import imaplib
import json
import mimetypes
import os
import re
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one, transaction
from .ha_auth import home_assistant_token
from .ha_entities import DEFAULT_GW2000_ENTITIES, resolve_gw2000_entities
from .service import estate_id, json_ready, new_id


INTAKE_ROOT = Path(os.environ.get("INTAKE_ROOT", "/data/intake"))
GW2000_ENTITIES = DEFAULT_GW2000_ENTITIES
PLANNING_ENTITIES = {
    "cover.sonoff_1001f2446e",
    "sensor.sonoff_1001f2446e_voltage_1",
    "sensor.sonoff_1001f2446e_current_1",
    "sensor.sonoff_1001f2446e_power_1",
    "sensor.sonoff_1001f2446e_energy_1",
    "sensor.total_solar_input_dc_kwh",
    "sensor.generator_main_breaker_phase_a_power",
    "sensor.generator_main_breaker_total_energy",
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def risk_level(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 35:
        return "moderate"
    return "low"


def _ha_get(path: str) -> Any:
    token = home_assistant_token()
    if not token:
        return None
    error: Exception | None = None
    for base in ("http://supervisor/core/api", "http://homeassistant:8123/api", "http://core-homeassistant:8123/api"):
        try:
            request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except Exception as current_error:
            error = current_error
    if error:
        raise error
    return None


def _ha_post(path: str, payload: dict[str, Any]) -> Any:
    token = home_assistant_token()
    if not token:
        return None
    request = urllib.request.Request("http://supervisor/core/api" + path, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"[]")


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gw2000_station() -> str:
    row = fetch_one("SELECT id FROM weather_stations WHERE estate_id=%s AND external_id='gw2000a'", (estate_id(),))
    if row:
        return row["id"]
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO weather_stations (id,estate_id,name,station_type,external_id,location_type,metadata) VALUES (%s,%s,'GW2000A','home_assistant','gw2000a','vineyard',JSON_OBJECT('source','Home Assistant recorder'))", (record_id, estate_id()))
    return record_id


def sync_home_assistant_weather() -> dict[str, Any]:
    if not home_assistant_token():
        return {"configured": False, "message": "Home Assistant supervisor access is not available"}
    station_id = _gw2000_station()
    states = _ha_get("/states") or []
    state_map = {row.get("entity_id"): row for row in states}
    gw2000_entities = resolve_gw2000_entities(states, get_settings().gw2000_entity_prefix)
    snapshot_at = datetime.now().replace(second=0, microsecond=0)
    with transaction() as (_, cursor):
        for entity_id in PLANNING_ENTITIES:
            item = state_map.get(entity_id)
            if not item:
                continue
            attributes = item.get("attributes") or {}
            cursor.execute(
                "INSERT IGNORE INTO planning_sensor_snapshots (estate_id,entity_id,recorded_at,state_value,numeric_value,unit,friendly_name,attributes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), entity_id, snapshot_at, str(item.get("state")), _numeric(item.get("state")), attributes.get("unit_of_measurement"), attributes.get("friendly_name"), json.dumps(attributes)),
            )
    values = {key: _numeric((state_map.get(entity) or {}).get("state")) for key, entity in gw2000_entities.items()}
    for key in GW2000_ENTITIES:
        values.setdefault(key, None)
    soil_values = [values.pop("soil_moisture_1"), values.pop("soil_moisture_2")]
    values["soil_moisture_pct"] = sum(v for v in soil_values if v is not None) / len([v for v in soil_values if v is not None]) if any(v is not None for v in soil_values) else None
    if any(value is not None for value in values.values()):
        observed_at = datetime.now().replace(second=0, microsecond=0)
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO weather_observations (estate_id,station_id,observed_at,temp_c,humidity_pct,pressure_hpa,wind_kph,wind_gust_kph,rain_mm,solar_wm2,uv_index,soil_moisture_pct,source_hash,raw_payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE temp_c=VALUES(temp_c),humidity_pct=VALUES(humidity_pct),pressure_hpa=VALUES(pressure_hpa),wind_kph=VALUES(wind_kph),wind_gust_kph=VALUES(wind_gust_kph),rain_mm=VALUES(rain_mm),solar_wm2=VALUES(solar_wm2),uv_index=VALUES(uv_index),soil_moisture_pct=VALUES(soil_moisture_pct),source_hash=VALUES(source_hash),raw_payload=VALUES(raw_payload)",
                (estate_id(), station_id, observed_at, values.get("temp_c"), values.get("humidity_pct"), values.get("pressure_hpa"), values.get("wind_kph"), values.get("wind_gust_kph"), values.get("rain_mm"), values.get("solar_wm2"), values.get("uv_index"), values.get("soil_moisture_pct"), digest, json.dumps(values)),
            )
    checkpoint = fetch_one("SELECT checkpoint_value FROM sync_checkpoints WHERE estate_id=%s AND integration_name='home_assistant_gw2000_history'", (estate_id(),))
    start = datetime.fromisoformat(checkpoint["checkpoint_value"]) if checkpoint and checkpoint.get("checkpoint_value") else datetime(2023, 1, 1)
    end = min(start + timedelta(days=14), datetime.now())
    if start < end and gw2000_entities:
        entity_list = ",".join(gw2000_entities.values())
        path = "/history/period/" + urllib.parse.quote(start.isoformat(), safe="-:T") + "?" + urllib.parse.urlencode({"end_time": end.isoformat(), "filter_entity_id": entity_list, "minimal_response": "", "no_attributes": ""})
        history = _ha_get(path) or []
        daily: dict[date, dict[str, list[float]]] = {}
        reverse = {entity: key for key, entity in gw2000_entities.items()}
        for series in history:
            if not series:
                continue
            key = reverse.get(series[0].get("entity_id"))
            if not key:
                continue
            for point in series:
                value = _numeric(point.get("state"))
                if value is None:
                    continue
                try:
                    day = datetime.fromisoformat(str(point.get("last_changed", "")).replace("Z", "+00:00")).date()
                except Exception:
                    continue
                daily.setdefault(day, {}).setdefault(key, []).append(value)
        with transaction() as (_, cursor):
            for day, fields in daily.items():
                temps = fields.get("temp_c", [])
                humidities = fields.get("humidity_pct", [])
                winds = fields.get("wind_gust_kph", []) + fields.get("wind_kph", [])
                rains = fields.get("rain_mm", [])
                solar = fields.get("solar_wm2", [])
                soils = fields.get("soil_moisture_1", []) + fields.get("soil_moisture_2", [])
                avg_temp = sum(temps) / len(temps) if temps else None
                gdd = max(0, avg_temp - 10) if avg_temp is not None else None
                cursor.execute(
                    "INSERT INTO weather_daily (estate_id,station_id,weather_date,temp_min_c,temp_avg_c,temp_max_c,humidity_avg_pct,rain_mm,wind_max_kph,solar_mj_m2,soil_moisture_avg_pct,gdd_base10) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE temp_min_c=VALUES(temp_min_c),temp_avg_c=VALUES(temp_avg_c),temp_max_c=VALUES(temp_max_c),humidity_avg_pct=VALUES(humidity_avg_pct),rain_mm=VALUES(rain_mm),wind_max_kph=VALUES(wind_max_kph),solar_mj_m2=VALUES(solar_mj_m2),soil_moisture_avg_pct=VALUES(soil_moisture_avg_pct),gdd_base10=VALUES(gdd_base10)",
                    (estate_id(), station_id, day, min(temps) if temps else None, avg_temp, max(temps) if temps else None, sum(humidities)/len(humidities) if humidities else None, max(rains) if rains else None, max(winds) if winds else None, (sum(solar)/len(solar))*0.0864 if solar else None, sum(soils)/len(soils) if soils else None, gdd),
                )
            cursor.execute("INSERT INTO sync_checkpoints (estate_id,integration_name,checkpoint_value,last_success_at,last_attempt_at,metadata) VALUES (%s,'home_assistant_gw2000_history',%s,NOW(),NOW(),%s) ON DUPLICATE KEY UPDATE checkpoint_value=VALUES(checkpoint_value),last_success_at=NOW(),last_attempt_at=NOW(),last_error=NULL,metadata=VALUES(metadata)", (estate_id(), end.isoformat(), json.dumps({"days": len(daily), "entities": list(gw2000_entities.values())})))
    return {"configured": True, "live_values": values, "history_through": end.isoformat()}


def calculate_disease_pressure(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    """Screening signals only; treatment decisions remain with the agronomist."""
    temp = float(metrics.get("temp_avg_c") or 0)
    max_temp = float(metrics.get("temp_max_c") or temp)
    humidity = float(metrics.get("humidity_avg_pct") or 0)
    rain = float(metrics.get("rain_72h_mm") or 0)
    soil = metrics.get("soil_moisture_avg_pct")
    soil_value = float(soil) if soil is not None else 35.0
    downy = _clamp((humidity - 60) * 1.35 + min(rain, 30) * 2.0 + (18 if 10 <= temp <= 28 else 0))
    powdery = _clamp((humidity - 45) * 0.85 + (30 if 18 <= temp <= 30 else 5) - min(rain, 20) * 0.45)
    botrytis = _clamp((humidity - 70) * 1.4 + min(rain, 35) * 1.45 + (18 if 15 <= temp <= 25 else 0))
    heat = _clamp((max_temp - 29) * 9 + max(0, 32 - soil_value) * 1.5)
    definitions = (
        ("downy_mildew", "Downy mildew", downy, "Scout susceptible blocks and review canopy wetness with Sebastian before any treatment decision."),
        ("powdery_mildew", "Powdery mildew", powdery, "Inspect shaded bunch zones and recent growth; ask Sebastian to confirm whether action is warranted."),
        ("botrytis", "Botrytis", botrytis, "Check bunch condition and airflow, especially after rain; record field evidence before deciding."),
        ("heat_stress", "Heat stress", heat, "Inspect vine and soil-water stress early in the day and review irrigation or protection priorities."),
    )
    return [
        {"disease_code": code, "disease_name": name, "risk_score": score, "risk_level": risk_level(score), "suggested_action": action}
        for code, name, score, action in definitions
    ]


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return None


def _meaningful_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in {"", "null", "none", "n/a", "unknown"} else text


def _has_weather_evidence(assessment: dict[str, Any]) -> bool:
    snapshot = assessment.get("input_snapshot")
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            snapshot = {}
    return isinstance(snapshot, dict) and any(snapshot.get(key) is not None for key in (
        "temp_avg_c", "temp_max_c", "humidity_avg_pct", "rain_72h_mm", "soil_moisture_avg_pct"
    ))


def predict_next_treatment(
    treatments: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    prediction_date: date | None = None,
) -> dict[str, Any]:
    """Predict the next review point, never an autonomous pesticide instruction."""
    today = prediction_date or date.today()
    planned: list[tuple[date, dict[str, Any]]] = []
    overdue: list[tuple[date, dict[str, Any]]] = []
    for row in treatments:
        if row.get("status") != "planned":
            continue
        planned_date = _date_value(row.get("planned_application_date") or row.get("application_date"))
        if not planned_date:
            continue
        (planned if planned_date >= today else overdue).append((planned_date, row))

    safety = "Sebastian/agronomist approval, current Italian label, PHI, REI, weather and PPE checks are required before application."
    if planned:
        planned_date, row = min(planned, key=lambda item: item[0])
        return {
            "type": "recorded_plan", "headline": _meaningful_text(row.get("purpose")) or "Recorded treatment plan",
            "timing_label": "Today" if planned_date == today else f"In {(planned_date - today).days} days",
            "window_start": planned_date, "window_end": planned_date, "confidence": "Recorded plan",
            "risk_level": "planned", "why": _meaningful_text(row.get("source_instructions")) or _meaningful_text(row.get("notes")) or "This date is already recorded in the vineyard plan.",
            "suggested_action": f"Confirm current field conditions and the recorded plan with Sebastian. {safety}",
            "agronomist_status": "approved" if row.get("agronomist_approved") else "pending",
            "requires_agronomist_approval": True, "source_record_id": row.get("id"),
        }
    overdue = [item for item in overdue if (today - item[0]).days <= 45]
    if overdue:
        planned_date, row = max(overdue, key=lambda item: item[0])
        return {
            "type": "overdue_verification", "headline": _meaningful_text(row.get("purpose")) or "Verify overdue treatment plan",
            "timing_label": f"Verify now · {(today - planned_date).days} days overdue",
            "window_start": today, "window_end": today, "confidence": "Recorded plan needs reconciliation",
            "risk_level": "high", "why": f"The planned date was {planned_date.isoformat()}, but the record is still marked planned.",
            "suggested_action": "Confirm whether it was completed, cancelled or rescheduled; do not duplicate an application. " + safety,
            "agronomist_status": "pending", "requires_agronomist_approval": True, "source_record_id": row.get("id"),
        }

    current = [row for row in assessments if row.get("disease_code") != "heat_stress"]
    if not current or not any(_has_weather_evidence(row) for row in current):
        return {
            "type": "insufficient_data", "headline": "No treatment prediction yet",
            "timing_label": "Waiting for current weather evidence", "window_start": None, "window_end": None,
            "confidence": "Insufficient data", "risk_level": "unknown",
            "why": "The disease model does not have enough current GW2000 weather evidence to support a timing estimate.",
            "suggested_action": "Check the weather sync and scout the vineyard. No treatment is recommended from missing data.",
            "agronomist_status": "not_required", "requires_agronomist_approval": True,
        }
    highest = max(current, key=lambda row: float(row.get("risk_score") or 0))
    level = highest.get("risk_level") or "low"
    windows = {"critical": (0, 1), "high": (1, 3), "moderate": (3, 7), "low": (7, 7)}
    start_days, end_days = windows.get(level, (7, 7))
    review_start, review_end = today + timedelta(days=start_days), today + timedelta(days=end_days)
    no_action = level == "low"
    return {
        "type": "monitor" if no_action else "field_review",
        "headline": "No treatment predicted from current evidence" if no_action else f"Review {highest.get('disease_name', 'disease')} risk with Sebastian",
        "timing_label": f"Reassess by {review_end.strftime('%d %b')}" if no_action else f"Field review {review_start.strftime('%d %b')}–{review_end.strftime('%d %b')}",
        "window_start": review_start, "window_end": review_end, "confidence": "Weather screening",
        "risk_level": level, "why": highest.get("evidence_summary") or "Current weather-based disease pressure screening.",
        "suggested_action": (highest.get("suggested_action") or "Scout susceptible blocks.") + " " + safety,
        "agronomist_status": highest.get("agronomist_status") or "pending",
        "requires_agronomist_approval": True, "source_assessment_id": highest.get("id"),
    }


def refresh_disease_pressure() -> list[dict[str, Any]]:
    row = fetch_one(
        "SELECT AVG(temp_c) temp_avg_c,MAX(temp_c) temp_max_c,AVG(humidity_pct) humidity_avg_pct,"
        "SUM(COALESCE(rain_mm,0)) rain_72h_mm,AVG(soil_moisture_pct) soil_moisture_avg_pct "
        "FROM weather_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 72 HOUR",
        (estate_id(),),
    ) or {}
    assessments = calculate_disease_pressure(row)
    now = datetime.now()
    evidence = (
        f"72 h weather: avg {float(row.get('temp_avg_c') or 0):.1f} C, max {float(row.get('temp_max_c') or 0):.1f} C, "
        f"humidity {float(row.get('humidity_avg_pct') or 0):.0f}%, rain {float(row.get('rain_72h_mm') or 0):.1f} mm."
    )
    with transaction() as (_, cursor):
        for item in assessments:
            record_id = new_id()
            cursor.execute(
                "INSERT INTO disease_pressure_assessments (id,estate_id,assessed_at,assessment_date,model_version,disease_code,disease_name,risk_score,risk_level,evidence_summary,suggested_action,input_snapshot) "
                "VALUES (%s,%s,%s,%s,'weather-screen-v1',%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE assessed_at=VALUES(assessed_at),risk_score=VALUES(risk_score),risk_level=VALUES(risk_level),evidence_summary=VALUES(evidence_summary),suggested_action=VALUES(suggested_action),input_snapshot=VALUES(input_snapshot)",
                (record_id, estate_id(), now, now.date(), item["disease_code"], item["disease_name"], item["risk_score"], item["risk_level"], evidence, item["suggested_action"], json.dumps(json_ready(row))),
            )
            source_id = f"pressure:{now.date()}:{item['disease_code']}"
            if item["risk_level"] in {"high", "critical"}:
                cursor.execute("SELECT id FROM alerts WHERE estate_id=%s AND source_id=%s AND status='open'", (estate_id(), source_id))
                if not cursor.fetchone():
                    alert_id = new_id()
                    cursor.execute("INSERT INTO alerts (id,estate_id,alert_type,severity,title,message,source,source_id,status,triggered_at,metadata) VALUES (%s,%s,'disease_pressure',%s,%s,%s,'operational-intelligence',%s,'open',NOW(),%s)", (alert_id, estate_id(), "critical" if item["risk_level"] == "critical" else "warning", f"{item['disease_name']} pressure {item['risk_level']}", item["suggested_action"], source_id, json.dumps(item)))
                    settings = get_settings()
                    if settings.ha_notifications_enabled and home_assistant_token():
                        try:
                            service = settings.ha_notify_service.strip("/")
                            _ha_post("/services/" + service, {"title": "Baiamonte vineyard alert", "message": f"{item['disease_name']}: {item['risk_level']} pressure. {item['suggested_action']}"})
                        except Exception:
                            pass
    return [{**item, "evidence_summary": evidence, "agronomist_status": "pending"} for item in assessments]


def save_intake_file(data: bytes, filename: str, media_type: str | None, source: str, title: str | None = None,
                     message_text: str | None = None, external_id: str | None = None,
                     sender_name: str | None = None, sender_address: str | None = None) -> str:
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Files must be 20 MB or smaller")
    digest = hashlib.sha256(data).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "upload").name)[:180]
    record_id = new_id()
    INTAKE_ROOT.mkdir(parents=True, exist_ok=True)
    path = INTAKE_ROOT / f"{record_id}-{safe_name}"
    path.write_bytes(data)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO intake_items (id,estate_id,source,external_id,sender_name,sender_address,received_at,title,message_text,original_filename,stored_path,media_type,file_sha256,classification,review_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,'unclassified','new')",
            (record_id, estate_id(), source, external_id, sender_name, sender_address, title, message_text, safe_name, str(path), media_type or mimetypes.guess_type(safe_name)[0], digest),
        )
    return record_id


def analyze_intake(record_id: str) -> dict[str, Any]:
    settings = get_settings()
    item = fetch_one("SELECT * FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not item:
        raise ValueError("Intake item not found")
    if not settings.openai_api_key:
        return {"configured": False, "message": "Add the OpenAI API key in app configuration to analyze this item."}
    prompt = (
        "Classify this Tenuta Baiamonte vineyard intake as one of lab_report, vineyard_instruction, cellar_instruction, "
        "labor_hours, completed_work, issue_or_decision, harvest_total, treatment_instruction, weather, olive_record, finance, or other. "
        "Extract only explicit facts and preserve names, dates, units, block, variety, lot and sender. Return JSON with classification, summary, "
        "facts, uncertainties, suggested_database_records, and required_human_review. Each suggested record must name the destination section and fields. "
        "Do not invent missing values. Never approve a treatment or lab correction; mark those agronomist_review_required or enologist_review_required."
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt + "\nMessage: " + (item.get("message_text") or "") }]
    path = Path(item["stored_path"]) if item.get("stored_path") else None
    if path and path.exists():
        raw = path.read_bytes()
        mime = item.get("media_type") or "application/octet-stream"
        encoded = base64.b64encode(raw).decode()
        if mime.startswith("image/"):
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
        else:
            content.append({"type": "input_file", "filename": item.get("original_filename") or "document", "file_data": f"data:{mime};base64,{encoded}"})
    request_body = json.dumps({"model": settings.openai_model, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_object"}}}).encode()
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=request_body, headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read())
        output_text = _response_text(result) or "{}"
        parsed = json.loads(output_text)
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET classification=%s,ai_summary=%s,extracted_data=%s,review_status='ready_for_review',processing_error=NULL WHERE id=%s", (parsed.get("classification"), parsed.get("summary"), json.dumps(parsed), record_id))
        return {"configured": True, "analysis": parsed}
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET review_status='failed',processing_error=%s WHERE id=%s", (str(error)[:1000], record_id))
        raise


def _response_text(result: dict[str, Any]) -> str:
    if result.get("output_text"):
        return str(result["output_text"])
    parts: list[str] = []
    for item in result.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def ask_assistant(question: str, language: str = "en", focus: str = "vineyard") -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"configured": False, "message": "Add the OpenAI API key in app configuration to ask vineyard questions."}
    context = {
        "weather_recent": json_ready(fetch_all("SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph,soil_moisture_pct FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 96", (estate_id(),))),
        "disease_pressure": json_ready(fetch_all("SELECT assessment_date,disease_name,risk_score,risk_level,evidence_summary,suggested_action,agronomist_status,agronomist_notes FROM disease_pressure_assessments WHERE estate_id=%s ORDER BY assessment_date DESC,risk_score DESC LIMIT 20", (estate_id(),))),
        "lab_flags": json_ready(fetch_all("SELECT lab_date,sample_name,analyte_name,numeric_value,unit,comparison_flag,decision_action FROM v_lab_comparison WHERE estate_id=%s AND comparison_flag IN ('review','high','low') ORDER BY lab_date DESC LIMIT 40", (estate_id(),))),
        "lab_recent": json_ready(fetch_all("SELECT lab_date,sample_name,sample_type,analyte_name,numeric_value,text_value,unit,comparison_flag,reference_min,reference_max FROM v_lab_comparison WHERE estate_id=%s ORDER BY lab_date DESC,sample_name,analyte_name LIMIT 120", (estate_id(),))),
        "planned_treatments": json_ready(fetch_all("SELECT application_date,purpose,block_code,products,agronomist_approved FROM v_treatment_history WHERE estate_id=%s AND status='planned' ORDER BY application_date LIMIT 30", (estate_id(),))),
        "treatment_history": json_ready(fetch_all("SELECT application_date,planned_application_date,purpose,block_code,products,source_doses,source_water_text,status,planned_by,assigned_to,agronomist_approved,actual_details_confirmed,source_instructions FROM v_treatment_history WHERE estate_id=%s ORDER BY application_date DESC LIMIT 60", (estate_id(),))),
        "open_work": json_ready(fetch_all("SELECT title,category,priority,due_date,block_code,status FROM v_open_work WHERE estate_id=%s ORDER BY due_date LIMIT 30", (estate_id(),))),
    }
    system = (
        "You are the Tenuta Baiamonte vineyard decision-support assistant. "
        f"The current question focus is {focus}. Answer from the supplied database context, distinguish facts from inference, "
        "and say when data is missing. Never approve or prescribe a pesticide treatment. Treatment suggestions must require Sebastian/agronomist review, "
        "current Italian label legality, PHI, REI, weather and PPE checks. Do not alter data."
        + (" Reply in Italian." if language == "it" else " Reply in English.")
    )
    request_body = json.dumps({"model": settings.openai_model, "input": [{"role": "developer", "content": system}, {"role": "user", "content": question + "\n\nCurrent database context:\n" + json.dumps(context)}]}).encode()
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=request_body, headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read())
    return {"configured": True, "answer": _response_text(result), "model": settings.openai_model}


def poll_gmail_once() -> int:
    settings = get_settings()
    if not settings.gmail_address or not settings.gmail_app_password:
        return 0
    allowed = {item.strip().casefold() for item in settings.gmail_allowed_senders.split(",") if item.strip()}
    saved = 0
    mailbox = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mailbox.login(settings.gmail_address, settings.gmail_app_password)
        mailbox.select(settings.gmail_folder or "INBOX", readonly=True)
        _, ids = mailbox.search(None, "UNSEEN")
        for message_id in (ids[0].split() if ids and ids[0] else [])[-50:]:
            external_id = message_id.decode()
            if fetch_one("SELECT id FROM intake_items WHERE estate_id=%s AND source='gmail' AND external_id LIKE %s", (estate_id(), external_id + ":%")):
                continue
            _, payload = mailbox.fetch(message_id, "(BODY.PEEK[])")
            raw = next((part[1] for part in payload if isinstance(part, tuple)), None)
            if not raw:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw)
            sender_name, sender_address = parseaddr(message.get("From", ""))
            if allowed and sender_address.casefold() not in allowed:
                continue
            body_part = message.get_body(preferencelist=("plain",))
            body_text = body_part.get_content() if body_part else ""
            parts = list(message.iter_attachments())
            if not parts and body_text.strip():
                record_id = save_intake_file(body_text.encode(), "message.txt", "text/plain", "gmail", message.get("Subject"), body_text, f"{external_id}:body", sender_name, sender_address)
                saved += 1
                if settings.openai_api_key:
                    try:
                        analyze_intake(record_id)
                    except Exception:
                        pass
            for part in parts:
                data = part.get_payload(decode=True) or b""
                if not data:
                    continue
                attachment_id = f"{external_id}:{part.get_filename() or saved}"
                record_id = save_intake_file(data, part.get_filename() or "attachment", part.get_content_type(), "gmail", message.get("Subject"), body_text, attachment_id, sender_name, sender_address)
                saved += 1
                if settings.openai_api_key:
                    try:
                        analyze_intake(record_id)
                    except Exception:
                        pass
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass
    return saved


async def integration_loop() -> None:
    settings = get_settings()
    counter = 0
    while True:
        try:
            await asyncio.to_thread(refresh_disease_pressure)
            if counter == 0 or counter >= max(1, settings.weather_sync_minutes):
                await asyncio.to_thread(sync_home_assistant_weather)
            if counter == 0 or counter >= max(1, settings.gmail_poll_minutes):
                await asyncio.to_thread(poll_gmail_once)
                counter = 0
        except Exception as error:
            try:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,error_message) VALUES (%s,'operational-intelligence','inbound','scheduled_sync','failed',%s)",
                        (estate_id(), str(error)[:1000]),
                    )
            except Exception:
                pass
        counter += 1
        await asyncio.sleep(60)
