"""Small-data harvest learning with explicit evidence gates.

The estate has only a few vintages, so this intentionally uses a robust,
auditable empirical model instead of a high-capacity black box.  It learns
both cumulative base-10 GDD at picking and the offset from the estate's
variety calendar anchor, then validates predictions by leaving each vintage
out in turn.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Any


MIN_TRAINING_ROWS = 3
MIN_TRAINING_YEARS = 2
MIN_WEATHER_DAYS = 90


def canonical_variety(value: Any) -> str:
    text = " ".join(str(value or "").casefold().replace("/", " ").replace("-", " ").split())
    if "nerello" in text:
        return "nerello mascalese"
    if "grenache" in text or "granache" in text:
        return "grenache"
    if "grecanico" in text:
        return "grecanico"
    return text


def daily_gdd(row: dict[str, Any], base_temp_c: float = 10.0) -> float | None:
    """Return one standardized Winkler-style daily GDD value."""
    low, high, mean = row.get("temp_min_c"), row.get("temp_max_c"), row.get("temp_avg_c")
    try:
        temperature = (float(low) + float(high)) / 2 if low is not None and high is not None else float(mean)
    except (TypeError, ValueError):
        return None
    return max(0.0, temperature - base_temp_c)


def build_gdd_curves(rows: list[dict[str, Any]], season_month: int = 3, season_day: int = 1) -> dict[int, list[tuple[date, float]]]:
    curves: dict[int, list[tuple[date, float]]] = {}
    totals: dict[int, float] = {}
    parsed: list[tuple[date, dict[str, Any]]] = []
    for row in rows:
        raw = row.get("weather_date")
        try:
            day = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
        if day < date(day.year, season_month, season_day):
            continue
        parsed.append((day, row))
    for day, row in sorted(parsed, key=lambda item: item[0]):
        value = daily_gdd(row)
        if value is None:
            continue
        totals[day.year] = totals.get(day.year, 0.0) + value
        curves.setdefault(day.year, []).append((day, totals[day.year]))
    return curves


def gdd_on(curve: list[tuple[date, float]], target_day: date) -> tuple[float | None, int]:
    eligible = [(day, total) for day, total in curve if day <= target_day]
    return (eligible[-1][1], len(eligible)) if eligible else (None, 0)


def date_at_gdd(curve: list[tuple[date, float]], target_gdd: float) -> date | None:
    return next((day for day, total in curve if total >= target_gdd), None)


def prepare_training_rows(
    harvest_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    curves: dict[int, list[tuple[date, float]]],
    anchors: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    """Deduplicate exact picks and attach standardized cumulative GDD."""
    candidates: dict[tuple[int, str], dict[str, Any]] = {}
    for priority, rows in ((1, summary_rows), (2, harvest_rows)):
        for row in rows:
            variety = canonical_variety(row.get("variety_name"))
            if not variety or variety not in anchors:
                continue
            try:
                year = int(row.get("vintage_year"))
                raw_day = row.get("pick_date")
                pick_day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10])
            except (TypeError, ValueError):
                continue
            if pick_day.year != year:
                continue
            cumulative_gdd, weather_days = gdd_on(curves.get(year, []), pick_day)
            if cumulative_gdd is None or weather_days < MIN_WEATHER_DAYS:
                continue
            month, day = anchors[variety]
            record = {
                "year": year,
                "variety": variety,
                "pick_date": pick_day,
                "pick_doy": pick_day.timetuple().tm_yday,
                "anchor_doy": date(year, month, day).timetuple().tm_yday,
                "anchor_offset_days": (pick_day - date(year, month, day)).days,
                "cumulative_gdd": cumulative_gdd,
                "weather_days": weather_days,
                "source": row.get("source") or ("harvest_lot" if priority == 2 else "vintage_summary"),
                "priority": priority,
            }
            key = (year, variety)
            if key not in candidates or priority > candidates[key]["priority"]:
                candidates[key] = record
    return [{key: value for key, value in row.items() if key != "priority"} for row in sorted(candidates.values(), key=lambda item: (item["year"], item["variety"]))]


def _estimate(records: list[dict[str, Any]], variety: str) -> dict[str, Any]:
    global_gdd = median(float(row["cumulative_gdd"]) for row in records)
    global_offset = median(float(row["anchor_offset_days"]) for row in records)
    direct = [row for row in records if row["variety"] == variety]
    # Shrink variety-specific evidence toward the estate result. Two seasons
    # receive 50% weight; more seasons progressively earn more influence.
    weight = len(direct) / (len(direct) + 2) if direct else 0.0
    direct_gdd = median(float(row["cumulative_gdd"]) for row in direct) if direct else global_gdd
    direct_offset = median(float(row["anchor_offset_days"]) for row in direct) if direct else global_offset
    return {
        "target_gdd": global_gdd * (1 - weight) + direct_gdd * weight,
        "anchor_offset_days": round(global_offset * (1 - weight) + direct_offset * weight),
        "variety_samples": len(direct),
        "scope": "variety_shrunk" if direct else "estate_pooled",
    }


def fit_harvest_model(
    records: list[dict[str, Any]],
    variety: str,
    current_year: int,
    anchor: date,
    curves: dict[int, list[tuple[date, float]]],
) -> dict[str, Any]:
    variety = canonical_variety(variety)
    years = sorted({int(row["year"]) for row in records})
    ready = len(records) >= MIN_TRAINING_ROWS and len(years) >= MIN_TRAINING_YEARS
    result: dict[str, Any] = {
        "model": "robust-harvest-ensemble-v1",
        "ready": ready,
        "training_samples": len(records),
        "training_years": years,
        "minimum_samples": MIN_TRAINING_ROWS,
        "minimum_years": MIN_TRAINING_YEARS,
        "missing_evidence": [],
    }
    if len(records) < MIN_TRAINING_ROWS:
        result["missing_evidence"].append(f"{MIN_TRAINING_ROWS - len(records)} more exact variety/year harvest record(s)")
    if len(years) < MIN_TRAINING_YEARS:
        result["missing_evidence"].append(f"exact harvest evidence from {MIN_TRAINING_YEARS - len(years)} more vintage(s)")
    if not ready:
        return result

    estimate = _estimate(records, variety)
    current_curve = curves.get(current_year, [])
    gdd_date = date_at_gdd(current_curve, estimate["target_gdd"])
    calendar_date = anchor + timedelta(days=estimate["anchor_offset_days"])
    learned_date = gdd_date or calendar_date
    if gdd_date:
        learned_date = date.fromordinal(round((gdd_date.toordinal() + calendar_date.toordinal()) / 2))

    errors: list[int] = []
    for held_out in records:
        training = [row for row in records if int(row["year"]) != int(held_out["year"])]
        if len(training) < 2 or len({int(row["year"]) for row in training}) < 1:
            continue
        held_estimate = _estimate(training, held_out["variety"])
        held_anchor = date(int(held_out["year"]), *anchors_for_variety(held_out["variety"]))
        held_gdd_date = date_at_gdd(curves.get(int(held_out["year"]), []), held_estimate["target_gdd"])
        held_calendar = held_anchor + timedelta(days=held_estimate["anchor_offset_days"])
        predicted = held_gdd_date or held_calendar
        if held_gdd_date:
            predicted = date.fromordinal(round((held_gdd_date.toordinal() + held_calendar.toordinal()) / 2))
        errors.append(abs((predicted - held_out["pick_date"]).days))
    mae_days = sum(errors) / len(errors) if errors else None
    confidence = "high" if mae_days is not None and mae_days <= 5 and len(years) >= 3 else "medium" if mae_days is not None and mae_days <= 10 else "low"
    return {
        **result,
        **estimate,
        "predicted_date": learned_date,
        "gdd_predicted_date": gdd_date,
        "calendar_predicted_date": calendar_date,
        "backtest_mae_days": round(mae_days, 1) if mae_days is not None else None,
        "backtest_predictions": len(errors),
        "confidence": confidence,
    }


_ANCHORS = {
    "grecanico": (9, 7),
    "grenache": (9, 14),
    "nerello mascalese": (9, 21),
}


def anchors_for_variety(variety: str) -> tuple[int, int]:
    return _ANCHORS.get(canonical_variety(variety), (9, 15))


HARVEST_ANCHORS = dict(_ANCHORS)


def summarize_lab_series(rows: list[dict[str, Any]], as_of: date, max_age_days: int = 21) -> dict[str, Any]:
    """Calculate auditable current laboratory features without inventing targets.

    The summary intentionally does not decide that fruit is ready. It supplies
    freshness, latest values and per-day trends to the bounded readiness review.
    """
    series: dict[str, list[tuple[date, float, dict[str, Any]]]] = {}
    for row in rows:
        raw_day, raw_value = row.get("lab_date"), row.get("numeric_value")
        try:
            day = raw_day.date() if isinstance(raw_day, datetime) else raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10])
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if day > as_of or (as_of - day).days > max_age_days:
            continue
        code = str(row.get("analyte_code") or row.get("analyte_name") or "").strip().casefold()
        if code:
            series.setdefault(code, []).append((day, value, row))
    features: dict[str, Any] = {}
    sample_dates: set[str] = set()
    for code, values in series.items():
        values.sort(key=lambda item: item[0])
        latest_day, latest_value, latest_row = values[-1]
        sample_dates.add(latest_day.isoformat())
        feature: dict[str, Any] = {
            "analyte_code": code,
            "analyte_name": latest_row.get("analyte_name"),
            "latest_value": latest_value,
            "unit": latest_row.get("unit"),
            "latest_date": latest_day,
            "age_days": (as_of - latest_day).days,
            "observations": len(values),
        }
        if len(values) >= 2:
            previous_day, previous_value, _ = values[-2]
            elapsed = (latest_day - previous_day).days
            if elapsed > 0:
                feature["previous_value"] = previous_value
                feature["previous_date"] = previous_day
                feature["change_per_day"] = round((latest_value - previous_value) / elapsed, 4)
                sample_dates.add(previous_day.isoformat())
        features[code] = feature
    freshest = min((item["age_days"] for item in features.values()), default=None)
    return {
        "usable": bool(features),
        "freshness_limit_days": max_age_days,
        "freshest_age_days": freshest,
        "sample_dates": sorted(sample_dates),
        "analytes": features,
    }


_LAB_ANALYTE_ALIASES = {
    "babo": "babo",
    "potential_alcohol": "potential_alcohol",
    "ph": "ph",
    "ta": "ta",
    "total_acidity": "ta",
    "total_acidity_tartaric": "ta",
    "malic": "malic",
    "l_malic_acid": "malic",
}

_LAB_DISTANCE_SCALES = {
    "babo": 2.0,
    "potential_alcohol": 1.3,
    "ph": 0.2,
    "ta": 2.5,
    "malic": 1.5,
}


def _lab_marker(code: Any) -> str | None:
    return _LAB_ANALYTE_ALIASES.get(str(code or "").strip().casefold())


def estimate_lab_pick_date(
    current_summary: dict[str, Any],
    historical_rows: list[dict[str, Any]],
    harvest_records: list[dict[str, Any]],
    variety: str,
) -> dict[str, Any]:
    """Estimate days to picking from like-for-like historical grape chemistry.

    This deliberately remains a small-data nearest-match model.  It uses only
    past measurements paired with an exact harvest date, requires at least two
    comparable maturity markers, and exposes every selected comparison.  The
    caller is responsible for bounding how far this evidence may move the
    broader weather/GDD forecast.
    """
    current: dict[str, float] = {}
    current_dates: list[date] = []
    for raw_code, feature in (current_summary.get("analytes") or {}).items():
        marker = _lab_marker(raw_code)
        if not marker or feature.get("latest_value") is None:
            continue
        try:
            current[marker] = float(feature["latest_value"])
            raw_day = feature.get("latest_date")
            current_dates.append(raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10]))
        except (TypeError, ValueError):
            continue
    sample_date = max(current_dates) if current_dates else None
    canonical = canonical_variety(variety)
    picks = {
        (int(row["year"]), canonical_variety(row.get("variety"))): row.get("pick_date")
        for row in harvest_records
        if row.get("year") is not None and row.get("pick_date") is not None
    }
    grouped: dict[tuple[int, date, str], dict[str, float]] = {}
    for row in historical_rows:
        marker = _lab_marker(row.get("analyte_code") or row.get("analyte_name"))
        sample_name = canonical_variety(row.get("sample_name"))
        if not marker or sample_name != canonical or row.get("numeric_value") is None:
            continue
        try:
            year = int(float(row.get("vintage_year")))
            raw_day = row.get("lab_date")
            lab_day = raw_day if isinstance(raw_day, date) else date.fromisoformat(str(raw_day)[:10])
            grouped.setdefault((year, lab_day, sample_name), {})[marker] = float(row["numeric_value"])
        except (TypeError, ValueError):
            continue
    comparisons: list[dict[str, Any]] = []
    for (year, lab_day, sample_name), values in grouped.items():
        pick_day = picks.get((year, sample_name))
        if isinstance(pick_day, datetime):
            pick_day = pick_day.date()
        elif pick_day and not isinstance(pick_day, date):
            try:
                pick_day = date.fromisoformat(str(pick_day)[:10])
            except ValueError:
                pick_day = None
        if not pick_day:
            continue
        days_to_pick = (pick_day - lab_day).days
        if not -3 <= days_to_pick <= 60:
            continue
        shared = sorted(set(current) & set(values))
        if len(shared) < 2:
            continue
        distance = sum(abs(current[key] - values[key]) / _LAB_DISTANCE_SCALES[key] for key in shared) / len(shared)
        comparisons.append({
            "vintage_year": year,
            "lab_date": lab_day,
            "harvest_date": pick_day,
            "days_to_harvest": days_to_pick,
            "shared_markers": shared,
            "distance": round(distance, 4),
        })
    comparisons.sort(key=lambda row: (row["distance"], -len(row["shared_markers"]), -row["vintage_year"]))
    selected = comparisons[:3]
    if not sample_date or not selected:
        return {
            "usable": False,
            "model": "historical-lab-nearest-match-v1",
            "reason": "No prior same-variety grape sample has at least two matching markers and an exact harvest date.",
            "comparisons": [],
        }
    # A weighted mean retains timing resolution while ensuring a close match
    # dominates a weaker one.  Limit weights so a near-zero distance cannot
    # numerically overwhelm all other evidence.
    weights = [1.0 / max(0.1, float(row["distance"])) for row in selected]
    days = round(sum(float(row["days_to_harvest"]) * weight for row, weight in zip(selected, weights)) / sum(weights))
    predicted = sample_date + timedelta(days=max(0, min(45, days)))
    return {
        "usable": True,
        "model": "historical-lab-nearest-match-v1",
        "sample_date": sample_date,
        "predicted_pick_date": predicted,
        "estimated_days_to_harvest": max(0, min(45, days)),
        "comparison_count": len(selected),
        "vintages": sorted({int(row["vintage_year"]) for row in selected}),
        "confidence": "medium" if len({int(row["vintage_year"]) for row in selected}) >= 2 else "low",
        "comparisons": selected,
        "policy": "Same-variety historical grape chemistry paired to exact harvest dates; minimum two markers.",
    }
