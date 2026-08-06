"""Presentation-safe, read-only data for the vineyard entrance display."""

from __future__ import annotations

from datetime import date
from typing import Any

from .db import fetch_all, fetch_one
from .service import estate_id, json_ready


def display_payload(year: int | None = None) -> dict[str, Any]:
    year = year or date.today().year
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    season_id = season.get("id", "")
    planned = (fetch_one("SELECT SUM(planned_kg) n FROM harvest_plans WHERE season_id=%s", (season_id,)) or {}).get("n")
    harvested = (fetch_one("SELECT SUM(weight_kg) n FROM harvest_lots WHERE season_id=%s", (season_id,)) or {}).get("n")
    completion = round(float(harvested or 0) / float(planned) * 100, 1) if planned else None
    return json_ready({
        "year": year,
        "dashboard": {
            "counts": {
                "open_tasks": (fetch_one("SELECT COUNT(*) n FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress')", (estate_id(),)) or {"n": 0})["n"],
                "harvest_kg": harvested,
                "work_hours": (fetch_one("SELECT SUM(labor_hours) n FROM work_activities WHERE season_id=%s", (season_id,)) or {}).get("n"),
                "open_alerts": (fetch_one("SELECT COUNT(*) n FROM alerts WHERE estate_id=%s AND status='open'", (estate_id(),)) or {"n": 0})["n"],
            },
            "tasks": fetch_all(
                "SELECT title,category,status,due_date,(SELECT code FROM vineyard_blocks WHERE id=tasks.block_id) block_code "
                "FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') ORDER BY due_date IS NULL,due_date LIMIT 6",
                (estate_id(),),
            ),
            "alerts": fetch_all("SELECT severity,title,'Vineyard attention item' message,triggered_at FROM alerts WHERE estate_id=%s AND status='open' ORDER BY triggered_at DESC LIMIT 6", (estate_id(),)),
            "weather": fetch_all("SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 48", (estate_id(),))[::-1],
        },
        "grapes": {
            "metrics": {
                "planned_kg": planned,
                "harvested_kg": harvested,
                "completion_pct": completion,
                "cellar_volume_l": (fetch_one("SELECT SUM(volume_l) n FROM wine_lots WHERE season_id=%s", (season_id,)) or {}).get("n"),
            },
            "varieties": fetch_all(
                "SELECT v.name,p.planned_kg,p.planned_pick_date,p.plan_status,h.harvested_kg,"
                "CASE WHEN p.planned_kg>0 THEN ROUND(COALESCE(h.harvested_kg,0)/p.planned_kg*100,1) ELSE NULL END completion_pct "
                "FROM grape_varieties v LEFT JOIN (SELECT variety_id,SUM(planned_kg) planned_kg,MIN(planned_pick_date) planned_pick_date,"
                "GROUP_CONCAT(DISTINCT status SEPARATOR ', ') plan_status FROM harvest_plans WHERE season_id=%s GROUP BY variety_id) p ON p.variety_id=v.id "
                "LEFT JOIN (SELECT variety_id,SUM(weight_kg) harvested_kg FROM harvest_lots WHERE season_id=%s GROUP BY variety_id) h ON h.variety_id=v.id "
                "WHERE v.estate_id=%s AND v.active=1 ORDER BY v.name",
                (season_id, season_id, estate_id()),
            ),
            "vintages": fetch_all("SELECT vintage_year,SUM(grapes_kg) grapes_kg,SUM(wine_l) wine_l FROM vintage_summaries WHERE estate_id=%s GROUP BY vintage_year ORDER BY vintage_year", (estate_id(),)),
        },
        "pressure": fetch_all(
            "SELECT disease_code,disease_name,risk_score,risk_level,agronomist_status FROM disease_pressure_assessments "
            "WHERE estate_id=%s AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date DESC,risk_score DESC LIMIT 16",
            (estate_id(),),
        ),
        "labs": {"queue": fetch_all(
            "SELECT CONCAT(UPPER(LEFT(sample_type,1)),SUBSTRING(sample_type,2),' sample') sample_name,sample_type,flagged_results,review_status,lab_date "
            "FROM v_lab_decision_queue WHERE estate_id=%s AND (flagged_results>0 OR review_status IN ('decision_needed','reviewing')) ORDER BY lab_date DESC LIMIT 6",
            (estate_id(),),
        )},
        "weather": fetch_all(
            "SELECT YEAR(weather_date) weather_year,MONTH(weather_date) weather_month,AVG(temp_avg_c) temp_avg_c "
            "FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date) BETWEEN %s AND %s GROUP BY YEAR(weather_date),MONTH(weather_date) ORDER BY weather_year,weather_month",
            (estate_id(), year - 3, year),
        ),
    })
