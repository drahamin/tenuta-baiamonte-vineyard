"""Bounded reported crop history. No inferred dates, totals or wine yields."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from ..db import fetch_all
from .mobile_cellar_projection import _id, _number
from .mobile_reporting_reads import ReportingSourceUnavailable

CONTRACT = "baiamonte.mobile-harvest-history.v1"
DATASETS = frozenset({"grapes", "vintages", "olives"})
MAX_ROWS = 1000
FIRST_YEAR = 2023


def _date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ReportingSourceUnavailable("unqualified history date")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            if date.fromisoformat(value).isoformat() == value:
                return value
        except ValueError:
            pass
    raise ReportingSourceUnavailable("invalid history date")


def project_history(rows: list[Mapping[str, Any]], estate: str, dataset: str,
                    from_year: int, to_year: int) -> list[dict[str, Any]]:
    _id(estate)
    if (dataset not in DATASETS or isinstance(from_year, bool) or isinstance(to_year, bool)
            or not isinstance(from_year, int) or not isinstance(to_year, int)
            or not FIRST_YEAR <= from_year <= to_year <= 2200):
        raise ValueError("invalid crop history boundary")
    if len(rows) > MAX_ROWS:
        raise ReportingSourceUnavailable("crop history exceeds read boundary")
    out, seen = [], set()
    for row in rows:
        year = row.get("vintage_year") if dataset != "olives" else row.get("record_year")
        if (row.get("estate_id") != estate or isinstance(year, bool) or not isinstance(year, int)
                or not from_year <= year <= to_year):
            raise ReportingSourceUnavailable("crop history estate/year mismatch")
        if dataset == "vintages":
            variety = row.get("variety_name")
            if not isinstance(variety, str) or not variety.strip() or len(variety) > 120:
                raise ReportingSourceUnavailable("invalid vintage source key")
            key = (year, variety)
            item = {"key": {"vintage_year": year, "variety_name": variety},
                    "reported_grapes_kg": _number(row.get("grapes_kg")),
                    "reported_wine_l": _number(row.get("wine_l")),
                    "evidence_status": row.get("evidence_status")}
        elif dataset == "grapes":
            key = _id(row.get("id"))
            if row.get("season_estate_id") != estate or row.get("variety_estate_id") != estate:
                raise ReportingSourceUnavailable("crop history join mismatch")
            item = {"id": key, "vintage_year": year, "season_id": _id(row.get("season_id")),
                    "variety_id": _id(row.get("variety_id")), "variety_name": row.get("variety_name"),
                    "harvest_date": _date(row.get("harvest_date")), "source_type": row.get("source_type"),
                    "reported_weight_kg": _number(row.get("weight_kg")),
                    "reported_crate_count": _number(row.get("crate_count"))}
        else:
            key = _id(row.get("id"))
            item = {"id": key, "record_year": year, "record_date": _date(row.get("record_date")),
                    "mill_date": _date(row.get("mill_date")),
                    "reported_olives_kg": _number(row.get("olives_harvested_kg")),
                    "reported_oil_l": _number(row.get("oil_liters")),
                    "reported_yield_pct": _number(row.get("yield_pct"))}
        if key in seen:
            raise ReportingSourceUnavailable("duplicate crop history source key")
        seen.add(key)
        out.append(item)
    return out


def read_history(estate: str, dataset: str, from_year: int, to_year: int) -> list[dict[str, Any]]:
    project_history([], estate, dataset, from_year, to_year)
    queries = {
        "grapes": (
            "SELECT h.id,h.estate_id,h.season_id,h.variety_id,DATE(h.harvested_at) harvest_date,"
            "h.source_type,h.weight_kg,h.crate_count,s.estate_id season_estate_id,s.vintage_year,"
            "v.estate_id variety_estate_id,v.name variety_name FROM harvest_lots h "
            "LEFT JOIN seasons s ON s.id=h.season_id AND s.estate_id=h.estate_id "
            "LEFT JOIN grape_varieties v ON v.id=h.variety_id AND v.estate_id=h.estate_id "
            "WHERE h.estate_id=%s AND (s.vintage_year BETWEEN %s AND %s OR s.id IS NULL) "
            "ORDER BY s.vintage_year,h.harvested_at,h.id LIMIT %s"
        ),
        "vintages": (
            "SELECT estate_id,vintage_year,variety_name,grapes_kg,wine_l,evidence_status "
            "FROM vintage_summaries WHERE estate_id=%s AND vintage_year BETWEEN %s AND %s "
            "ORDER BY vintage_year,variety_name LIMIT %s"
        ),
        "olives": (
            "SELECT id,estate_id,record_year,record_date,mill_date,olives_harvested_kg,oil_liters,yield_pct "
            "FROM olive_records WHERE estate_id=%s AND record_year BETWEEN %s AND %s "
            "ORDER BY record_year,record_date,id LIMIT %s"
        ),
    }
    rows = fetch_all(queries[dataset], (estate, from_year, to_year, MAX_ROWS + 1))
    return project_history(rows, estate, dataset, from_year, to_year)
