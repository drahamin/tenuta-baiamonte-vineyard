"""Bounded mobile reporting reads, independent of TV/HA/planning caches.

Authorization stays in mobile_site_routes before these functions are called.
Only approved reporting sources and explicit scalar fields are selected.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ..db import fetch_all, fetch_one


OBJECTS = frozenset({"tasks", "alerts", "issues", "labs", "cellar", "grapes"})


class ReportingSourceUnavailable(RuntimeError):
    pass


def _scope(estate: str, year: int, limit: int) -> None:
    if str(UUID(estate)) != estate:
        raise ValueError("invalid estate boundary")
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2200:
        raise ValueError("invalid estate year")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("invalid reporting limit")


_CONTAINER_FROM = (
    " FROM cellar_containers c LEFT JOIN wine_lots w ON w.id=("
    "SELECT MIN(wx.id) FROM wine_lots wx JOIN seasons s ON s.id=wx.season_id AND s.estate_id=wx.estate_id "
    "WHERE wx.estate_id=c.estate_id AND wx.current_container_id=c.id AND s.vintage_year=%s "
    "HAVING COUNT(*)=1) "
)
_CONTAINER_BASE = "c.id,c.code,c.name,w.stage,c.capacity_l,c.status"


def read_catalog(estate: str, year: int) -> dict[str, Any]:
    _scope(estate, year, 100)
    row = fetch_one("SELECT name FROM estates WHERE id=%s", (estate,)) or {}
    varieties = fetch_all(
        "SELECT id,name FROM grape_varieties WHERE estate_id=%s AND active=1 "
        "AND LOWER(name) NOT IN ('blend','other') ORDER BY name,id LIMIT %s", (estate, 50),
    )
    containers = fetch_all(
        "SELECT " + _CONTAINER_BASE + _CONTAINER_FROM +
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code,c.id LIMIT %s", (year, estate, 100),
    )
    return {"estate": {"name": row.get("name"), "location": "Contrada Baiamonte · Randazzo · Etna", "year": year},
            "varieties": varieties, "containers": containers}


def read_records(object_name: str, estate: str, year: int, limit: int) -> list[dict[str, Any]]:
    _scope(estate, year, limit)
    if object_name not in OBJECTS:
        raise ValueError("unapproved reporting object")
    if object_name == "tasks":
        return fetch_all(
            "SELECT t.id,t.title,t.category,t.status,t.priority,t.due_date,t.updated_at,b.code block_code "
            "FROM tasks t LEFT JOIN vineyard_blocks b ON b.id=t.block_id AND b.estate_id=t.estate_id "
            "WHERE t.estate_id=%s AND t.status IN ('planned','in_progress') "
            "ORDER BY FIELD(t.priority,'urgent','high','normal','low'),t.due_date IS NULL,t.due_date,t.id LIMIT %s",
            (estate, limit),
        )
    if object_name == "alerts":
        return fetch_all(
            "SELECT id,alert_type,severity,title,message,status,triggered_at,resolved_at FROM alerts "
            "WHERE estate_id=%s AND status='open' "
            "ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC,id LIMIT %s", (estate, limit),
        )
    if object_name == "issues":
        return fetch_all(
            "SELECT id,issue_text,issue_type,priority,status,due_date,subject_ref,decision_action "
            "FROM issues_decisions WHERE estate_id=%s AND status IN ('open','monitoring') "
            "ORDER BY FIELD(priority,'critical','high','medium','low'),due_date IS NULL,due_date,opened_date DESC,id LIMIT %s",
            (estate, limit),
        )
    if object_name == "labs":
        # Inspect only the permitted filtered view; never fall back to its
        # excluded/unfiltered underlying view if schema differs or is absent.
        columns = {row["column_name"] for row in fetch_all(
            "SELECT COLUMN_NAME column_name FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name=%s", ("ro_lab_decision_queue",),
        )}
        identifier = "sample_id" if "sample_id" in columns else "id" if "id" in columns else None
        if identifier is None or not {"estate_id", "sample_type", "flagged_results", "review_status", "lab_date"} <= columns:
            raise ReportingSourceUnavailable("permitted lab reporting schema unavailable")
        # identifier is selected from two literal identifiers, never a caller value.
        return fetch_all(
            f"SELECT {identifier} id,CONCAT(UPPER(LEFT(sample_type,1)),SUBSTRING(sample_type,2),' sample') sample_name,"
            "sample_type,flagged_results,review_status,lab_date FROM ro_lab_decision_queue "
            "WHERE estate_id=%s AND (flagged_results>0 OR review_status IN ('decision_needed','reviewing')) "
            "ORDER BY lab_date DESC,id LIMIT %s", (estate, limit),
        )
    if object_name == "cellar":
        return fetch_all(
            # Multiple current links are unknown, never resolved to a winner.
            # Lot-only observations and unlinked manual profiles cannot prove
            # a measurement belongs to this container; keep its fields unknown.
            "SELECT " + _CONTAINER_BASE + ",w.volume_l,"
            "CASE WHEN c.capacity_l>0 AND w.volume_l IS NOT NULL "
            "THEN ROUND(w.volume_l/c.capacity_l*100,1) ELSE NULL END fill_pct,"
            "NULL temperature_c,NULL density_sg,NULL brix,NULL ph,NULL observed_at" +
            _CONTAINER_FROM +
            "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code,c.id LIMIT %s", (year, estate, limit),
        )
    return fetch_all(
        "SELECT v.id,v.name,p.planned_kg,h.harvested_kg,h.first_pick_date,h.last_pick_date,"
        "CASE WHEN p.planned_kg>0 AND h.estate_harvested_kg IS NOT NULL "
        "THEN ROUND(h.estate_harvested_kg/p.planned_kg*100,1) ELSE NULL END completion_pct "
        "FROM grape_varieties v LEFT JOIN (SELECT p.variety_id,SUM(p.planned_kg) planned_kg "
        "FROM harvest_plans p JOIN seasons s ON s.id=p.season_id AND s.estate_id=p.estate_id "
        "WHERE p.estate_id=%s AND s.vintage_year=%s GROUP BY p.variety_id) p ON p.variety_id=v.id "
        "LEFT JOIN (SELECT h.variety_id,SUM(h.weight_kg) harvested_kg,"
        "SUM(CASE WHEN h.source_type='purchased' THEN 0 ELSE h.weight_kg END) estate_harvested_kg,"
        "DATE(MIN(h.harvested_at)) first_pick_date,DATE(MAX(h.harvested_at)) last_pick_date "
        "FROM harvest_lots h JOIN seasons s ON s.id=h.season_id AND s.estate_id=h.estate_id "
        "WHERE h.estate_id=%s AND s.vintage_year=%s GROUP BY h.variety_id) h ON h.variety_id=v.id "
        "WHERE v.estate_id=%s AND v.active=1 AND LOWER(v.name) NOT IN ('blend','other') "
        "ORDER BY v.name,v.id LIMIT %s", (estate, year, estate, year, estate, limit),
    )
