from __future__ import annotations

from typing import Any

from .db import fetch_all, fetch_one
from .service import estate_id


_TOTAL_LABELS = {"vintage total", "total", "totale vendemmia"}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def is_vintage_total(name: Any) -> bool:
    return str(name or "").strip().casefold() in _TOTAL_LABELS


def selected_vintage_rows(year: int) -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,evidence_status,reconciliation_note FROM vintage_summaries WHERE estate_id=%s AND vintage_year=%s ORDER BY variety_name",
        (estate_id(), year),
    )


def selected_dashboard_history(year: int, season_id: str) -> dict[str, Any]:
    harvest = fetch_all("SELECT * FROM v_harvest_summary WHERE estate_id=%s AND vintage_year=%s ORDER BY variety_name", (estate_id(), year))
    summaries = selected_vintage_rows(year)
    totals = reconciled_vintage_values(summaries)
    recorded_kg = (fetch_one("SELECT COALESCE(SUM(weight_kg),0) n FROM harvest_lots WHERE season_id=%s", (season_id,)) or {"n": 0})["n"]
    weather = fetch_all(
        "SELECT weather_date observed_at,temp_avg_c temp_c,humidity_avg_pct humidity_pct,rain_mm,wind_max_kph wind_kph,soil_moisture_avg_pct soil_moisture_pct FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date)=%s ORDER BY weather_date",
        (estate_id(), year),
    ) or fetch_all(
        "SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph,soil_moisture_pct FROM weather_observations WHERE estate_id=%s AND YEAR(observed_at)=%s ORDER BY observed_at",
        (estate_id(), year),
    )
    return {"harvest": harvest or historical_harvest_rows(summaries), "weather": weather, "totals": totals, "recorded_kg": recorded_kg, "has_summary": bool(summaries)}


def reconciled_vintage_values(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """Prefer the workbook's reconciled total; otherwise sum component varieties."""
    total = next((row for row in rows if is_vintage_total(row.get("variety_name"))), None)
    components = [row for row in rows if not is_vintage_total(row.get("variety_name"))]

    def value(field: str) -> float | None:
        if total and total.get(field) is not None:
            return _number(total[field])
        values = [_number(row[field]) for row in components if row.get(field) is not None]
        return sum(values) if values else None

    return {field: value(field) for field in ("grapes_kg", "wine_l", "cassette_count")}


def historical_harvest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    components = [row for row in rows if not is_vintage_total(row.get("variety_name"))]
    source = components or [row for row in rows if is_vintage_total(row.get("variety_name"))]
    return [{
        "variety_name": row.get("variety_name"), "total_kg": row.get("grapes_kg"),
        "total_crates": row.get("cassette_count"), "first_pick_date": None,
        "last_pick_date": None, "historical_summary": True,
        "evidence_status": row.get("evidence_status"),
        "reconciliation_note": row.get("reconciliation_note"),
    } for row in source if row.get("grapes_kg") is not None or row.get("cassette_count") is not None]


def merge_variety_summaries(varieties: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay display-only historical totals without inventing harvest lots or dates."""
    by_name = {str(row.get("name") or "").strip().casefold(): row for row in varieties}
    for summary in summaries:
        if is_vintage_total(summary.get("variety_name")):
            continue
        name = str(summary.get("variety_name") or "").strip()
        if not name:
            continue
        row = by_name.get(name.casefold())
        if row is None:
            row = {"id": f"historical:{name.casefold()}", "name": name}
            varieties.append(row)
            by_name[name.casefold()] = row
        if row.get("harvested_kg") is None:
            row["harvested_kg"] = summary.get("grapes_kg")
        if row.get("crates") is None:
            row["crates"] = summary.get("cassette_count")
        row.update({
            "historical_wine_l": summary.get("wine_l"), "historical_summary": True,
            "evidence_status": summary.get("evidence_status"),
            "reconciliation_note": summary.get("reconciliation_note"),
        })
    return varieties


def merge_cellar_history(history: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_year = {int(row["vintage_year"]): row for row in history}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in summaries:
        grouped.setdefault(int(row["vintage_year"]), []).append(row)
    for year, rows in grouped.items():
        item = by_year.setdefault(year, {"vintage_year": year})
        totals = reconciled_vintage_values(rows)
        if not _number(item.get("fruit_kg")):
            item["fruit_kg"] = totals["grapes_kg"]
        if not _number(item.get("volume_l")):
            item["volume_l"] = totals["wine_l"]
        item["historical_summary"] = True
    return [by_year[year] for year in sorted(by_year)]


def merge_variety_history(history: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {(int(row["vintage_year"]), str(row.get("variety_name") or "").strip().casefold()): row for row in history}
    for summary in summaries:
        if is_vintage_total(summary.get("variety_name")):
            continue
        key = (int(summary["vintage_year"]), str(summary.get("variety_name") or "").strip().casefold())
        row = keyed.setdefault(key, {"vintage_year": key[0], "variety_name": summary.get("variety_name")})
        if not _number(row.get("harvested_kg")):
            row["harvested_kg"] = summary.get("grapes_kg")
        if not _number(row.get("crates")):
            row["crates"] = summary.get("cassette_count")
        row["historical_summary"] = True
    return sorted(keyed.values(), key=lambda row: (int(row["vintage_year"]), str(row.get("variety_name") or "")))
