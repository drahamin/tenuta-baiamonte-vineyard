from __future__ import annotations

import re
from math import ceil
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


def canonical_variety_key(name: Any) -> str:
    value = str(name or "").strip().casefold()
    value = re.sub(r"\s*(?:/|-|\()\s*(?:red|white|rosso|bianco)\)?\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_variety_label(name: Any) -> str:
    value = str(name or "").strip()
    return re.sub(r"\s*(?:/|-|\()\s*(?:red|white|rosso|bianco)\)?\s*$", "", value, flags=re.IGNORECASE).strip()


def selected_vintage_rows(year: int) -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_id,source_note_name FROM vintage_summaries WHERE estate_id=%s AND vintage_year=%s ORDER BY variety_name",
        (estate_id(), year),
    )


def all_vintage_rows() -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_id,source_note_name FROM vintage_summaries WHERE estate_id=%s ORDER BY vintage_year,variety_name",
        (estate_id(),),
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


def historical_activity_rows(year: int) -> list[dict[str, Any]]:
    """Return source-traceable prior work without pretending costs are hours."""
    rows = fetch_all(
        "SELECT id,record_date,record_year,period_start_year,period_end_year,date_precision,"
        "record_kind,classification,actor_name,description,amount_eur,labor_hours,payment_status,"
        "source_file_name,source_sheet FROM historical_cost_records "
        "WHERE estate_id=%s AND (included_in_totals=1 OR labor_hours IS NOT NULL) "
        "AND (record_kind IN ('expense','compensation') OR labor_hours IS NOT NULL) "
        "AND (record_year=%s OR (record_year IS NULL AND %s BETWEEN period_start_year AND period_end_year)) "
        "ORDER BY COALESCE(record_date,MAKEDATE(COALESCE(record_year,period_end_year),1)) DESC,source_row_number DESC LIMIT 100",
        (estate_id(), year, year),
    )
    return [{
        "id": row["id"],
        "activity_date": row.get("record_date") if row.get("date_precision") == "day" else None,
        "record_date": row.get("record_date"),
        "record_year": row.get("record_year"),
        "period_start_year": row.get("period_start_year"),
        "period_end_year": row.get("period_end_year"),
        "date_precision": row.get("date_precision") or "unknown",
        "title": row.get("description"),
        "category": row.get("classification") or row.get("record_kind") or "historical",
        "status": "historical",
        "labor_hours": row.get("labor_hours"),
        "actor_name": row.get("actor_name"),
        "amount_eur": row.get("amount_eur"),
        "payment_status": row.get("payment_status"),
        "historical_record": True,
        "source_file_name": row.get("source_file_name"),
        "source_sheet": row.get("source_sheet"),
    } for row in rows]


def historical_activity_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe legacy work coverage without treating missing hours as zero."""
    records = len(rows)
    known_hour_rows = sum(row.get("labor_hours") is not None for row in rows)
    exact_date_rows = sum(row.get("date_precision") == "day" and row.get("record_date") is not None for row in rows)
    month_date_rows = sum(row.get("date_precision") == "month" for row in rows)
    broad_date_rows = sum(row.get("date_precision") in {"year", "period", "unknown"} for row in rows)
    known_hours = sum(float(row.get("labor_hours") or 0) for row in rows)
    if not records:
        hour_status = "not_available"
    elif known_hour_rows == records:
        hour_status = "complete"
    elif known_hour_rows:
        hour_status = "partial"
    else:
        hour_status = "not_recorded"
    return {
        "records": records,
        "known_hours": known_hours,
        "known_hour_records": known_hour_rows,
        "hour_status": hour_status,
        "exact_date_records": exact_date_rows,
        "month_date_records": month_date_rows,
        "broad_date_records": broad_date_rows,
    }


def historical_note_facts(year: int, domain: str | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = (estate_id(), year)
    domain_filter = ""
    if domain:
        domain_filter = " AND domain=%s"
        params += (domain,)
    return fetch_all(
        "SELECT fact_date,fact_year,date_precision,domain,subject,quantity_value,quantity_unit,details,"
        "evidence_status,source_note_name,conflict_note,canonical_table,canonical_key "
        "FROM historical_note_facts WHERE estate_id=%s AND fact_year=%s" + domain_filter +
        " ORDER BY fact_date IS NULL,fact_date,domain,subject",
        params,
    )


def historical_cellar_summary(year: int, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    summary = reconciled_vintage_values(rows) if rows else None
    facts = historical_note_facts(year, "cellar")
    if facts:
        summary = summary or {}
        summary["bottled_750ml"] = sum(float(row.get("quantity_value") or 0) for row in facts if str(row.get("quantity_unit") or "").casefold().startswith("750ml")) or None
        summary["source_facts"] = facts
    return summary


def merge_historical_work_overview(years: dict[int, dict[str, Any]], from_year: int, to_year: int) -> None:
    """Merge single-year and explicitly unsplit period records into coverage counts."""
    for row in fetch_all(
        "SELECT record_year year,COUNT(*) historical_work_records,"
        "SUM(labor_hours IS NOT NULL) historical_known_hour_records,SUM(labor_hours) historical_labor_hours,"
        "SUM(date_precision='day' AND record_date IS NOT NULL) historical_exact_date_records,"
        "SUM(date_precision='month') historical_month_date_records,"
        "SUM(date_precision IN ('year','period','unknown')) historical_broad_date_records "
        "FROM historical_cost_records WHERE estate_id=%s AND record_year BETWEEN %s AND %s "
        "AND (included_in_totals=1 OR labor_hours IS NOT NULL) "
        "AND (record_kind IN ('expense','compensation') OR labor_hours IS NOT NULL) GROUP BY record_year",
        (estate_id(), from_year, to_year),
    ):
        year = int(row.pop("year"))
        years[year].update(row)
    period_rows = fetch_all(
        "SELECT period_start_year,period_end_year FROM historical_cost_records WHERE estate_id=%s "
        "AND record_year IS NULL AND period_start_year<=%s AND period_end_year>=%s "
        "AND (included_in_totals=1 OR labor_hours IS NOT NULL) "
        "AND (record_kind IN ('expense','compensation') OR labor_hours IS NOT NULL)",
        (estate_id(), to_year, from_year),
    )
    for row in period_rows:
        for year in range(max(from_year, int(row["period_start_year"])), min(to_year, int(row["period_end_year"])) + 1):
            item = years[year]
            item["historical_work_records"] = int(item.get("historical_work_records") or 0) + 1
            item["historical_broad_date_records"] = int(item.get("historical_broad_date_records") or 0) + 1


def merge_historical_fact_overview(years: dict[int, dict[str, Any]], from_year: int, to_year: int) -> None:
    for row in fetch_all("SELECT fact_year year,COUNT(*) historical_fact_records FROM historical_note_facts WHERE estate_id=%s AND fact_year BETWEEN %s AND %s GROUP BY fact_year", (estate_id(), from_year, to_year)):
        years[int(row.pop("year"))].update(row)


def selected_dashboard_activities(year: int, season_id: str) -> dict[str, Any]:
    activities = fetch_all(
        "SELECT a.id,a.activity_date,a.title,a.category,a.status,a.labor_hours,b.code block_code "
        "FROM work_activities a LEFT JOIN vineyard_blocks b ON b.id=a.block_id "
        "WHERE a.estate_id=%s AND YEAR(a.activity_date)=%s ORDER BY a.activity_date DESC LIMIT 100",
        (estate_id(), year),
    )
    historical = historical_activity_rows(year)
    audit = historical_activity_audit(historical)
    labor = fetch_all(
        "SELECT id,work_date activity_date,COALESCE(NULLIF(work_performed,''),NULLIF(shift_label,''),CONCAT('Labor · ',person_or_crew)) title,"
        "COALESCE(NULLIF(work_category,''),'labor') category,COALESCE(NULLIF(approval_status,''),'recorded') status,"
        "COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) labor_hours,person_or_crew actor_name,entry_source,payment_status "
        "FROM labor_entries WHERE estate_id=%s AND YEAR(work_date)=%s ORDER BY work_date DESC,id DESC",
        (estate_id(), year),
    )
    for row in labor:
        row["labor_entry"] = True
    activities.extend(historical)
    activities.extend(labor)
    activities.sort(key=lambda row: str(row.get("activity_date") or row.get("record_date") or f"{row.get('period_end_year') or row.get('record_year') or 0}-01-01"), reverse=True)
    activity_hours = float((fetch_one("SELECT COALESCE(SUM(labor_hours),0) n FROM work_activities WHERE season_id=%s", (season_id,)) or {"n": 0})["n"] or 0)
    labor_hours = sum(float(row.get("labor_hours") or 0) for row in labor)
    return {
        "activities": activities[:100],
        "historical_records": len(historical),
        "labor_records": len(labor),
        "work_records": len(activities),
        "historical_audit": audit,
        "work_hours": (labor_hours if labor else activity_hours) + audit["known_hours"],
    }


def historical_forecast_evidence(year: int, vintages: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    conversion, production_audit = forecast_conversion_audit(year, vintages)
    weather = fetch_all(
        "SELECT YEAR(weather_date) weather_year,COUNT(*) observed_days,SUM(rain_mm) rain_mm,"
        "AVG(temp_avg_c) temp_avg_c,SUM(gdd_base10) gdd_base10 FROM weather_daily "
        "WHERE estate_id=%s AND YEAR(weather_date)<%s GROUP BY YEAR(weather_date) ORDER BY weather_year",
        (estate_id(), year),
    )
    lab_years = fetch_all(
        "SELECT COALESCE(vintage_year,YEAR(lab_date)) evidence_year,sample_type,COUNT(*) samples,COUNT(DISTINCT laboratory) laboratories "
        "FROM lab_samples WHERE estate_id=%s AND COALESCE(vintage_year,YEAR(lab_date))<%s "
        "GROUP BY COALESCE(vintage_year,YEAR(lab_date)),sample_type ORDER BY evidence_year,sample_type",
        (estate_id(), year),
    )
    maturity_years = fetch_all(
        "SELECT s.vintage_year evidence_year,COUNT(*) samples,COUNT(DISTINCT m.variety_id) varieties "
        "FROM maturity_samples m JOIN seasons s ON s.id=m.season_id WHERE m.estate_id=%s AND s.vintage_year<%s "
        "GROUP BY s.vintage_year ORDER BY s.vintage_year",
        (estate_id(), year),
    )
    exact_pick_years = fetch_all(
        "SELECT vintage_year evidence_year,COUNT(*) sourced_dates FROM vintage_summaries "
        "WHERE estate_id=%s AND vintage_year<%s AND first_pick_date IS NOT NULL AND harvest_date_precision='day' "
        "GROUP BY vintage_year ORDER BY vintage_year",
        (estate_id(), year),
    )
    return conversion, {
        **production_audit,
        "weather_years": weather,
        "laboratory_years": lab_years,
        "maturity_years": maturity_years,
        "exact_pick_years": exact_pick_years,
        "conversion_method": "weighted reconciled wine liters divided by reconciled grape kilograms",
    }


def reconciled_vintage_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one authoritative production row per vintage, never totals plus components."""
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["vintage_year"]), []).append(row)
    history = []
    for vintage_year, vintage_rows in sorted(grouped.items()):
        totals = reconciled_vintage_values(vintage_rows)
        history.append({
            "vintage_year": vintage_year,
            **totals,
            "evidence_status": ", ".join(sorted({str(row.get("evidence_status") or "").strip() for row in vintage_rows if row.get("evidence_status")})),
            "reconciliation_note": "; ".join(str(row.get("reconciliation_note") or "").strip() for row in vintage_rows if row.get("reconciliation_note")),
        })
    return history


def _forecast_exclusion_reason(row: dict[str, Any]) -> str | None:
    evidence = str(row.get("evidence_status") or "").casefold()
    note = str(row.get("reconciliation_note") or "").casefold()
    if "reported - review" in evidence or "use cautiously" in note or "unusually high" in note:
        return "Reported liquid volume requires reconciliation before model use"
    return None


def forecast_conversion_audit(year: int, vintages: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    """Select trusted pre-target vintages and walk-forward test the conversion model."""
    candidates = sorted(
        (row for row in vintages if row.get("grapes_kg") and row.get("wine_l") and int(row["vintage_year"]) < year),
        key=lambda row: int(row["vintage_year"]),
    )
    rows: list[dict[str, Any]] = []
    excluded = []
    for row in candidates:
        reason = _forecast_exclusion_reason(row)
        if reason:
            excluded.append({"vintage_year": int(row["vintage_year"]), "reason": reason})
        else:
            rows.append(row)
    grapes = sum(float(row["grapes_kg"]) for row in rows)
    wine = sum(float(row["wine_l"]) for row in rows)
    conversion = wine / grapes if grapes else 0.70
    backtest = []
    for index, actual in enumerate(rows[1:], start=1):
        training = rows[:index]
        training_grapes = sum(float(row["grapes_kg"]) for row in training)
        training_wine = sum(float(row["wine_l"]) for row in training)
        predicted = float(actual["grapes_kg"]) * training_wine / training_grapes
        actual_wine = float(actual["wine_l"])
        error_pct = abs(predicted - actual_wine) / actual_wine * 100 if actual_wine else 0
        backtest.append({
            "vintage_year": int(actual["vintage_year"]),
            "predicted_wine_l": round(predicted, 1),
            "actual_wine_l": actual_wine,
            "absolute_error_pct": round(error_pct, 1),
        })
    mean_error = sum(row["absolute_error_pct"] for row in backtest) / len(backtest) if backtest else None
    maximum_error = max((row["absolute_error_pct"] for row in backtest), default=15.0)
    range_pct = min(30, max(15, int(ceil(maximum_error / 5) * 5)))
    confidence = "low" if len(rows) < 4 or len(backtest) < 3 else "medium" if (mean_error or 100) <= 15 else "low"
    return conversion, {
        "production_vintages": [int(row["vintage_year"]) for row in rows],
        "excluded_production_vintages": excluded,
        "production_grapes_kg": grapes,
        "production_wine_l": wine,
        "conversion_backtest": backtest,
        "conversion_mean_absolute_error_pct": round(mean_error, 1) if mean_error is not None else None,
        "recommended_scenario_range_pct": range_pct,
        "production_model_confidence": confidence,
    }


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
    result = [{
            "variety_name": canonical_variety_label(row.get("variety_name")), "total_kg": row.get("grapes_kg"),
        "total_crates": row.get("cassette_count"), "first_pick_date": row.get("first_pick_date"),
        "last_pick_date": row.get("last_pick_date"), "historical_summary": True,
        "harvest_date_precision": row.get("harvest_date_precision") or "unknown",
        "source_note_name": row.get("source_note_name"),
        "evidence_status": row.get("evidence_status"),
        "reconciliation_note": row.get("reconciliation_note"),
    } for row in source if row.get("grapes_kg") is not None or row.get("cassette_count") is not None]
    # Harvest sequence is chronological when a source date exists; undated
    # summaries remain represented afterward instead of receiving fake dates.
    result.sort(key=lambda row: (row.get("first_pick_date") is None, str(row.get("first_pick_date") or "9999-12-31"), str(row.get("variety_name") or "").casefold()))
    return result


def merge_variety_summaries(varieties: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay display-only historical totals without inventing harvest lots or dates."""
    by_name = {canonical_variety_key(row.get("name")): row for row in varieties}
    for summary in summaries:
        if is_vintage_total(summary.get("variety_name")):
            continue
        name = str(summary.get("variety_name") or "").strip()
        if not name:
            continue
        key = canonical_variety_key(name)
        row = by_name.get(key)
        if row is None:
            row = {"id": f"historical:{key}", "name": canonical_variety_label(name)}
            varieties.append(row)
            by_name[key] = row
        if row.get("harvested_kg") is None:
            row["harvested_kg"] = summary.get("grapes_kg")
        if row.get("crates") is None:
            row["crates"] = summary.get("cassette_count")
        row.update({
            "historical_wine_l": summary.get("wine_l"), "historical_summary": True,
            "first_pick_date": row.get("first_pick_date") or summary.get("first_pick_date"),
            "last_pick_date": row.get("last_pick_date") or summary.get("last_pick_date"),
            "harvest_date_precision": summary.get("harvest_date_precision") or "unknown",
            "source_note_name": summary.get("source_note_name"),
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
    keyed = {(int(row["vintage_year"]), canonical_variety_key(row.get("variety_name"))): row for row in history}
    for summary in summaries:
        if is_vintage_total(summary.get("variety_name")):
            continue
        key = (int(summary["vintage_year"]), canonical_variety_key(summary.get("variety_name")))
        row = keyed.setdefault(key, {"vintage_year": key[0], "variety_name": canonical_variety_label(summary.get("variety_name"))})
        if not _number(row.get("harvested_kg")):
            row["harvested_kg"] = summary.get("grapes_kg")
        if not _number(row.get("crates")):
            row["crates"] = summary.get("cassette_count")
        row["first_pick_date"] = row.get("first_pick_date") or summary.get("first_pick_date")
        row["last_pick_date"] = row.get("last_pick_date") or summary.get("last_pick_date")
        row["source_note_name"] = summary.get("source_note_name")
        row["historical_summary"] = True
    return sorted(keyed.values(), key=lambda row: (int(row["vintage_year"]), str(row.get("variety_name") or "")))
