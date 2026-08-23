"""Cross-domain, evidence-backed learning health for the Admin AI console."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from ..db import fetch_all, fetch_one
from ..intelligence import disease_pressure_learning_status, treatment_learning_status
from ..service import estate_id, json_ready
from .laboratory import lab_learning_status
from .treatments import _agronomist_programs, agronomist_program_backtest
from .advanced_learning import advanced_learning_statuses
from .cistern_learning import cistern_learning_status


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _metric(label: str, value: Any, unit: str = "", target: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "target": target}


def _cistern() -> dict[str, Any]:
    model = cistern_learning_status()
    validation = model.get("validation_metrics") or {}
    quality = model.get("data_quality_snapshot") or {}
    historical = validation.get("historical_backfill") or {}
    all_history = validation.get("all_history") or historical
    live = validation.get("live_shadow") or {}
    validated = model.get("model_status") == "validated"
    issues = list(quality.get("release_issues") or [])
    if not model:
        issues = ["The cistern history has not been backfilled yet."]
    return {
        "code": "cistern", "name": "Cistern level shadow learning", "domain": "Water & Energy",
        "model_version": model.get("model_version") or "cistern-robust-rate-shadow-v1",
        "model_type": "Robust local rate model beside Camera AI",
        "status": "validated" if validated else "learning" if model else "waiting",
        "status_label": "Validated · eligible for bounded use" if validated else "Shadow mode · Camera AI remains authoritative" if model else "Waiting for backfill",
        "primary_metric": _metric("All-data walk-forward error", all_history.get("mae_points"), " points", "≤ 3 points"),
        "metrics": [
            _metric("Historical comparisons", historical.get("cases") or 0, "", "≥ 24"),
            _metric("Historical within ±5", historical.get("within_five_points_pct"), "%", "≥ 90%"),
            _metric("New live comparisons", live.get("cases") or 0, "", "≥ 12"),
            _metric("Observed changes", quality.get("changed_observations") or 0, "", "≥ 6"),
            _metric("Distinct levels", quality.get("distinct_levels") or 0, "", "≥ 4"),
            _metric("Live error", live.get("mae_points"), " points", "≤ 3 points"),
            _metric("Usable observations", quality.get("eligible_observations") or 0),
        ],
        "data_through": model.get("data_through"), "trained_at": model.get("trained_at"),
        "validation_method": validation.get("method") or "Strict walk-forward backfill followed by forward/live scoring.",
        "issues": issues,
    }


def _lab() -> dict[str, Any]:
    model = lab_learning_status()
    validation = model.get("validation_metrics") or {}
    quality = model.get("data_quality_snapshot") or {}
    accuracy = validation.get("direction_accuracy_pct")
    enough_cases = int(model.get("observed_outcome_count") or 0) >= int(quality.get("minimum_validation_cases") or 8)
    enough_vintages = int(model.get("represented_vintage_count") or 0) >= int(quality.get("minimum_validation_vintages") or 2)
    ready = enough_cases and enough_vintages and accuracy is not None and float(accuracy) >= float(validation.get("validation_direction_threshold_pct") or 60)
    issues = []
    if not enough_cases:
        issues.append("More observed walk-forward outcomes are required.")
    if not enough_vintages:
        issues.append("More vintages are required for durable validation.")
    if accuracy is not None and not ready:
        issues.append("Direction accuracy is below the 60% release threshold; projections remain review-gated.")
    return {
        "code": "laboratory", "name": "Laboratory vintage learning", "domain": "Enology",
        "model_version": model.get("model_version") or "not trained", "model_type": "Historical walk-forward learning",
        "status": "validated" if ready else "attention" if model else "waiting",
        "status_label": "Validated" if ready else "Learning · review required" if model else "Waiting for training",
        "primary_metric": _metric("Direction accuracy", accuracy, "%", "≥ 60%"),
        "metrics": [
            _metric("Observed outcomes", model.get("observed_outcome_count") or 0),
            _metric("Projection cases", model.get("projection_case_count") or 0),
            _metric("Numeric results", model.get("numeric_result_count") or 0),
            _metric("Vintages", model.get("represented_vintage_count") or 0, "", "≥ 2"),
        ],
        "data_through": model.get("data_through"), "trained_at": model.get("trained_at"),
        "validation_method": validation.get("method") or "Historical walk-forward without future leakage.",
        "issues": issues,
    }


def _treatments() -> dict[str, Any]:
    model = treatment_learning_status()
    quality = model.get("data_quality_snapshot") or {}
    validation = model.get("validation_metrics") or {}
    scales = (model.get("parameters_snapshot") or {}).get("weather_scales")
    backtest = agronomist_program_backtest(_agronomist_programs(), scales)
    recall = backtest.get("average_recall_pct") if backtest.get("replay_count") else None
    behavior_ready = bool(validation.get("behavior_ready"))
    outcome_ready = bool(validation.get("outcome_ready"))
    issues = []
    if not behavior_ready:
        minimum = quality.get("minimum_for_behavior_validation") or {"cases": 8, "seasons": 2}
        issues.append(f"Needs at least {minimum.get('cases', 8)} behavior cases across {minimum.get('seasons', 2)} seasons.")
    if not outcome_ready:
        minimum = (quality.get("minimum_for_outcome_validation") or {}).get("field_observed_outcomes", 4)
        issues.append(f"Needs at least {minimum} comparable field-observed outcomes.")
    return {
        "code": "treatments", "name": "Agronomist treatment learning", "domain": "Agronomy",
        "model_version": model.get("model_version") or "not trained", "model_type": "Weather-conditioned case learning",
        "status": "validated" if behavior_ready and outcome_ready else "learning" if model else "waiting",
        "status_label": "Validated" if behavior_ready and outcome_ready else "Learning · human approval required" if model else "Waiting for training",
        "primary_metric": _metric("Historical product recall", recall, "%", "leave-one-treatment-out"),
        "metrics": [
            _metric("Behavior cases", model.get("behavior_case_count") or 0, "", "≥ 8"),
            _metric("Field outcomes", model.get("outcome_case_count") or 0, "", "≥ 4"),
            _metric("Seasons", model.get("season_count") or 0, "", "≥ 2"),
            _metric("Backtest replays", backtest.get("replay_count") or 0),
            _metric("Exact programs", backtest.get("exact_program_count") or 0),
            _metric("Weather history", quality.get("historical_weather_days") or 0, " days"),
        ],
        "data_through": model.get("data_through"), "trained_at": model.get("trained_at"),
        "validation_method": backtest.get("method") or validation.get("readiness_note"), "issues": issues,
    }


def _harvest() -> dict[str, Any]:
    rows = fetch_all(
        "SELECT v.name variety_name,g.computed_at,g.observed_through,g.calibration_evidence "
        "FROM gdd_forecasts g JOIN grape_varieties v ON v.id=g.variety_id "
        "JOIN (SELECT variety_id,MAX(computed_at) computed_at FROM gdd_forecasts WHERE estate_id=%s GROUP BY variety_id) latest "
        "ON latest.variety_id=g.variety_id AND latest.computed_at=g.computed_at WHERE g.estate_id=%s",
        (estate_id(), estate_id()),
    )
    learned = []
    for row in rows:
        calibration = _mapping(row.get("calibration_evidence"))
        model = calibration.get("learned_model") or {}
        if model:
            learned.append({**model, "variety": row.get("variety_name"), "computed_at": row.get("computed_at"), "observed_through": row.get("observed_through")})
    ready = [row for row in learned if row.get("ready")]
    errors = [float(row["backtest_mae_days"]) for row in ready if row.get("backtest_mae_days") is not None]
    mae = round(sum(errors) / len(errors), 1) if errors else None
    samples = max((int(row.get("training_samples") or 0) for row in learned), default=0)
    years = sorted({int(year) for row in learned for year in (row.get("training_years") or [])})
    issues = []
    if not ready:
        issues.append("No variety yet meets the minimum exact multi-vintage harvest evidence gate.")
    elif mae is None:
        issues.append("The learned model is ready but has no usable leave-one-vintage-out score.")
    return {
        "code": "harvest", "name": "Harvest date learning", "domain": "Vintage",
        "model_version": next((row.get("model") for row in learned if row.get("model")), "robust-harvest-ensemble-v1"),
        "model_type": "Robust GDD + calendar ensemble",
        "status": "validated" if ready and mae is not None and mae <= 10 else "attention" if ready and mae is not None else "learning" if learned else "waiting",
        "status_label": (f"{len(ready)} of {len(learned)} varieties ready" if mae is None or mae <= 10 else f"Backtest error {mae} days · review required") if learned else "Waiting for forecasts",
        "primary_metric": _metric("Backtest mean error", mae, " days", "≤ 10 days"),
        "metrics": [_metric("Varieties tracked", len(learned)), _metric("Models ready", len(ready)), _metric("Exact records", samples, "", "≥ 3"), _metric("Vintages", len(years), "", "≥ 2")],
        "data_through": max((row.get("observed_through") for row in learned if row.get("observed_through")), default=None),
        "trained_at": max((row.get("computed_at") for row in learned if row.get("computed_at")), default=None),
        "validation_method": "Leave-one-vintage-out backtest; absolute picking-date error in days.", "issues": issues,
    }


def _disease() -> dict[str, Any]:
    model = disease_pressure_learning_status()
    summary = fetch_one(
        "SELECT COUNT(*) total,COUNT(DISTINCT assessment_date) days,MAX(assessed_at) assessed_at,MAX(assessment_date) data_through," 
        "SUM(agronomist_status IN ('approved','modified','rejected')) reviewed FROM disease_pressure_assessments WHERE estate_id=%s",
        (estate_id(),),
    ) or {}
    latest = fetch_one(
        "SELECT model_version FROM disease_pressure_assessments WHERE estate_id=%s ORDER BY assessed_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    total, reviewed = int(summary.get("total") or 0), int(summary.get("reviewed") or 0)
    review_pct = round(reviewed / total * 100, 1) if total else None
    validation = model.get("validation_metrics") or {}
    quality = model.get("data_quality_snapshot") or {}
    cases = int(model.get("training_case_count") or 0)
    validated = model.get("model_status") == "validated"
    issues = []
    if cases < int(quality.get("minimum_validation_cases") or 8):
        issues.append("Needs at least 8 comparable Agronomist or field-scouting labels.")
    if int(model.get("season_count") or 0) < int(quality.get("minimum_validation_seasons") or 2):
        issues.append("Needs labeled evidence across at least 2 seasons.")
    if cases and validation.get("improves_or_matches_baseline") is False:
        issues.append("Held-out calibration does not yet improve the rules baseline; learned adjustments remain provisional.")
    return {
        "code": "disease", "name": "Disease pressure intelligence", "domain": "Agronomy",
        "model_version": model.get("model_version") or latest.get("model_version") or "evidence-screen-v3", "model_type": "Weather rules + bounded outcome calibration",
        "status": "validated" if validated else "learning" if total else "waiting",
        "status_label": "Validated calibration" if validated else "Learning · rules baseline remains active" if total else "Waiting for assessments",
        "primary_metric": _metric("Held-out calibration error", validation.get("calibrated_mae_points"), " points", "≤ rules baseline"),
        "metrics": [_metric("Training labels", cases, "", "≥ 8"), _metric("Agronomist labels", model.get("agronomist_case_count") or 0), _metric("Field labels", model.get("scouting_case_count") or 0), _metric("Seasons", model.get("season_count") or 0, "", "≥ 2"), _metric("Review coverage", review_pct, "%")],
        "data_through": model.get("data_through") or summary.get("data_through"), "trained_at": model.get("trained_at") or summary.get("assessed_at"),
        "validation_method": validation.get("method") or "Rules baseline; calibration waits for comparable field labels.",
        "issues": issues if total else ["No disease pressure assessment has been recorded."],
    }


def _advanced(code: str, name: str, domain: str, metric_label: str, metric_key: str, unit: str, target: str) -> dict[str, Any]:
    model = advanced_learning_statuses().get(code) or {}
    validation = model.get("validation_metrics") or {}
    quality = model.get("data_quality_snapshot") or {}
    status = str(model.get("model_status") or "waiting")
    value = validation.get(metric_key)
    if value is None:
        value = quality.get(metric_key)
    issues = []
    if status != "validated":
        issues.append("Learning remains review-gated until its evidence and validation thresholds are met.")
    if code == "data_quality" and int(quality.get("open_findings") or 0):
        issues.append(f"{int(quality.get('open_findings') or 0)} adaptive data-quality finding(s) need review.")
    return {
        "code": code, "name": name, "domain": domain,
        "model_version": model.get("model_version") or "not trained", "model_type": {
            "disease_onset": "Walk-forward disease threshold forecast",
            "treatment_effectiveness": "Paired field-outcome profiles",
            "product_duration": "Observed duration and retreatment cadence",
            "resistance_rotation": "Chronological FRAC rotation learning",
            "young_vine_nutrition": "Young-vine nutrition outcome learning",
            "data_quality": "Adaptive anomaly and reliability detection",
            "block_disease_calibration": "Localized block disease calibration",
            "spray_window": "Outcome-conditioned spray-window learning",
        }[code],
        "status": "validated" if status == "validated" else "learning" if status not in {"waiting", "unavailable"} else status,
        "status_label": "Validated" if status == "validated" else "Learning · human review required" if status != "waiting" else "Waiting for evidence",
        "primary_metric": _metric(metric_label, value, unit, target),
        "metrics": [_metric("Training cases", model.get("case_count") or 0), _metric("Seasons", model.get("season_count") or 0, "", "≥ 2")],
        "data_through": model.get("data_through"), "trained_at": model.get("trained_at"),
        "validation_method": validation.get("method") or "Waiting for a durable model rebuild.", "issues": issues,
    }


def learning_monitor() -> dict[str, Any]:
    builders: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("laboratory", _lab), ("treatments", _treatments), ("harvest", _harvest), ("disease", _disease), ("cistern", _cistern),
        ("disease_onset", lambda: _advanced("disease_onset", "Disease-onset forecasting", "Agronomy", "Direction accuracy", "direction_accuracy_pct", "%", "≥ 60%")),
        ("treatment_effectiveness", lambda: _advanced("treatment_effectiveness", "Treatment effectiveness", "Agronomy", "Field-observed cases", "field_observed_cases", "", "≥ 8")),
        ("product_duration", lambda: _advanced("product_duration", "Product duration & cadence", "Agronomy", "Duration intervals", "duration_intervals", "", "≥ 6")),
        ("resistance_rotation", lambda: _advanced("resistance_rotation", "Resistance rotation", "Agronomy", "FRAC coverage", "frac_coverage_pct", "%", "≥ 80%")),
        ("young_vine_nutrition", lambda: _advanced("young_vine_nutrition", "Young-vine nutrition", "Agronomy", "Comparable outcomes", "comparable_outcomes", "", "≥ 4")),
        ("data_quality", lambda: _advanced("data_quality", "Adaptive data quality", "System", "Open findings", "open_findings", "", "0")),
        ("block_disease_calibration", lambda: _advanced("block_disease_calibration", "Block-specific disease calibration", "Agronomy", "Localized scouting cases", "localized_scouting_cases", "", "≥ 12")),
        ("spray_window", lambda: _advanced("spray_window", "Spray-window learning", "Agronomy", "Field-observed cases", "field_observed_cases", "", "≥ 8")),
    ]
    models = []
    for code, builder in builders:
        try:
            models.append(builder())
        except Exception as error:  # Keep one unavailable model from hiding the whole console.
            models.append({
                "code": code, "name": code.replace("_", " ").title(), "domain": "System", "model_version": "unavailable",
                "model_type": "Status unavailable", "status": "unavailable", "status_label": "Monitor query failed",
                "primary_metric": _metric("Accuracy", None), "metrics": [], "data_through": None, "trained_at": None,
                "validation_method": "No metric available.", "issues": [f"{type(error).__name__}: status could not be read."],
            })
    counts = {status: sum(1 for row in models if row.get("status") == status) for status in ("validated", "learning", "attention", "rules", "waiting", "unavailable")}
    overall = "attention" if counts["attention"] or counts["unavailable"] else "learning" if counts["learning"] or counts["waiting"] else "healthy"
    return json_ready({
        "generated_at": datetime.now(), "overall_status": overall, "models": models,
        "summary": {"model_count": len(models), **counts},
        "definitions": {
            "accuracy": "Only a held-out or future-outcome comparison is labeled accuracy or error.",
            "learning": "Learning remains review-gated until each model's minimum evidence threshold is met.",
            "freshness": "Data through is the newest evidence included; trained at is when the model or score was last rebuilt.",
        },
    })
