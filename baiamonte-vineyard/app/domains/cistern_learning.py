"""Leakage-safe shadow learning for the camera-estimated cistern level.

The camera result remains authoritative.  This local model is deliberately
kept in shadow until both historical walk-forward and genuinely forward/live
comparisons satisfy the release gate.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..service import estate_id, json_ready, new_id


MODEL_VERSION = "cistern-robust-rate-shadow-v1"
MIN_BACKFILL_CASES = 24
MIN_LIVE_CASES = 12
MIN_LIVE_UNIQUE_FRAMES = 6
MIN_CHANGED_EVENTS = 6
MIN_LIVE_CHANGED_EVENTS = 3
MIN_DISTINCT_LEVELS = 4
MAX_MAE_POINTS = 3.0
MIN_WITHIN_FIVE_PCT = 90.0


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


def _moment(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = []
    seen: set[tuple[datetime, float]] = set()
    for raw in rows:
        try:
            when = _moment(raw.get("observed_at"))
            level = max(0.0, min(100.0, float(raw.get("level_percent"))))
            confidence = float(raw.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if confidence < 0.35:
            continue
        key = (when, round(level, 2))
        if key in seen:
            continue
        seen.add(key)
        usable.append({**raw, "observed_at": when, "level_percent": level, "confidence": confidence})
    return sorted(usable, key=lambda row: (row["observed_at"], str(row.get("id") or "")))


def predict_from_history(history: list[dict[str, Any]], prediction_for: Any) -> dict[str, Any] | None:
    """Predict one target using only prior observations.

    The robust recent rate learns gradual drawdown while excluding refill and
    likely image-analysis jumps. Persistence is intentionally dominant because
    the camera-derived series is noisy and safety matters more than novelty.
    """
    rows = _eligible(history)
    target = _moment(prediction_for)
    rows = [row for row in rows if row["observed_at"] < target]
    if not rows:
        return None
    latest = rows[-1]
    horizon_hours = max(0.0, (target - latest["observed_at"]).total_seconds() / 3600)
    rates: list[float] = []
    sequence = rows[-13:]
    for left, right in zip(sequence, sequence[1:]):
        hours = (right["observed_at"] - left["observed_at"]).total_seconds() / 3600
        change = right["level_percent"] - left["level_percent"]
        if 0.08 <= hours <= 48 and abs(change) <= 8:
            rates.append(change / hours)
    learned_rate = statistics.median(rates) if rates else 0.0
    learned_rate = max(-0.75, min(0.75, learned_rate))
    # Shrink the learned rate and bound extrapolation; the latest accepted
    # camera value remains the strongest evidence.
    projected_change = max(-5.0, min(5.0, learned_rate * horizon_hours * 0.35))
    predicted = max(0.0, min(100.0, latest["level_percent"] + projected_change))
    return {
        "predicted_level_percent": round(predicted, 2),
        "evidence_through": latest["observed_at"],
        "horizon_minutes": max(0, round(horizon_hours * 60)),
        "learned_rate_points_per_hour": round(learned_rate, 4),
        "recent_rate_count": len(rates),
        "prior_observation_count": len(rows),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [float(row["absolute_error_points"]) for row in rows if row.get("absolute_error_points") is not None]
    return {
        "cases": len(errors),
        "mae_points": round(sum(errors) / len(errors), 2) if errors else None,
        "within_five_points_pct": round(sum(error <= 5 for error in errors) / len(errors) * 100, 1) if errors else None,
        "maximum_error_points": round(max(errors), 2) if errors else None,
    }


def release_gate(backfill: dict[str, Any], live: dict[str, Any], quality: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    quality = quality or {}
    reasons = []
    if int(backfill.get("cases") or 0) < MIN_BACKFILL_CASES:
        reasons.append(f"Needs at least {MIN_BACKFILL_CASES} historical walk-forward comparisons.")
    if int(live.get("cases") or 0) < MIN_LIVE_CASES:
        reasons.append(f"Needs at least {MIN_LIVE_CASES} new forward/live comparisons.")
    if quality and int(quality.get("live_unique_image_frames") or 0) < MIN_LIVE_UNIQUE_FRAMES:
        reasons.append(f"Needs at least {MIN_LIVE_UNIQUE_FRAMES} new unique camera frames; repeated frames do not prove learning.")
    if quality and int(quality.get("changed_observations") or 0) < MIN_CHANGED_EVENTS:
        reasons.append(f"Needs at least {MIN_CHANGED_EVENTS} observed level changes; stable repeats do not prove learning.")
    if quality and int(quality.get("live_changed_observations") or 0) < MIN_LIVE_CHANGED_EVENTS:
        reasons.append(f"Needs at least {MIN_LIVE_CHANGED_EVENTS} new live level changes.")
    if quality and int(quality.get("distinct_levels") or 0) < MIN_DISTINCT_LEVELS:
        reasons.append(f"Needs at least {MIN_DISTINCT_LEVELS} distinct observed levels.")
    for label, metric in (("Historical", backfill), ("Live", live)):
        if metric.get("mae_points") is not None and float(metric["mae_points"]) > MAX_MAE_POINTS:
            reasons.append(f"{label} mean error is above {MAX_MAE_POINTS:.0f} percentage points.")
        if metric.get("within_five_points_pct") is not None and float(metric["within_five_points_pct"]) < MIN_WITHIN_FIVE_PCT:
            reasons.append(f"{label} agreement within 5 points is below {MIN_WITHIN_FIVE_PCT:.0f}%.")
    return not reasons, reasons


def prepare_cistern_shadow_prediction(prediction_for: datetime | None = None) -> dict[str, Any] | None:
    """Create an auditable forecast before the next camera result exists."""
    target = prediction_for or datetime.now()
    raw = fetch_all(
        "SELECT id,observed_at,level_percent,confidence,source,image_sha256 FROM cistern_level_estimates "
        "WHERE estate_id=%s ORDER BY observed_at,id",
        (estate_id(),),
    )
    prediction = predict_from_history(raw, target)
    if not prediction:
        return None
    return {**prediction, "generated_at": datetime.now(), "prediction_for": target}


def refresh_cistern_learning(live_estimate_id: str | None = None, live_prediction: dict[str, Any] | None = None) -> dict[str, Any]:
    estate = estate_id()
    raw = fetch_all(
        "SELECT id,observed_at,level_percent,confidence,source,image_sha256 FROM cistern_level_estimates "
        "WHERE estate_id=%s ORDER BY observed_at,id",
        (estate,),
    )
    rows = _eligible(raw)
    existing = fetch_all(
        "SELECT target_estimate_id,prediction_kind FROM cistern_shadow_predictions WHERE estate_id=%s AND model_version=%s",
        (estate, MODEL_VERSION),
    )
    recorded = {str(row["target_estimate_id"]): str(row["prediction_kind"]) for row in existing}
    generated_at = datetime.now()
    inserts: list[tuple[Any, ...]] = []
    for index, target in enumerate(rows):
        target_id = str(target.get("id") or "")
        if not target_id or target_id in recorded:
            continue
        prediction = live_prediction if live_estimate_id and target_id == live_estimate_id else predict_from_history(rows[:index], target["observed_at"])
        if not prediction:
            continue
        kind = "live_shadow" if live_estimate_id and target_id == live_estimate_id else "historical_backfill"
        error = abs(float(prediction["predicted_level_percent"]) - float(target["level_percent"]))
        evidence = {key: value for key, value in prediction.items() if key not in {"predicted_level_percent", "evidence_through", "horizon_minutes"}}
        inserts.append((
            new_id(), estate, target_id, MODEL_VERSION, kind, prediction.get("generated_at") or generated_at, prediction["evidence_through"],
            target["observed_at"], prediction["horizon_minutes"], prediction["predicted_level_percent"],
            target["level_percent"], round(error, 2), json.dumps(json_ready(evidence)),
        ))
    if inserts:
        with transaction() as (_, cursor):
            cursor.executemany(
                "INSERT INTO cistern_shadow_predictions "
                "(id,estate_id,target_estimate_id,model_version,prediction_kind,generated_at,evidence_through,prediction_for,horizon_minutes,predicted_level_percent,observed_level_percent,absolute_error_points,evidence_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                inserts,
            )
    comparisons = fetch_all(
        "SELECT target_estimate_id,prediction_kind,predicted_level_percent,observed_level_percent,absolute_error_points FROM cistern_shadow_predictions WHERE estate_id=%s AND model_version=%s ORDER BY prediction_for",
        (estate, MODEL_VERSION),
    )
    backfill = _metrics([row for row in comparisons if row.get("prediction_kind") == "historical_backfill"])
    live = _metrics([row for row in comparisons if row.get("prediction_kind") == "live_shadow"])
    all_history = _metrics(comparisons)
    prior_by_id = {str(rows[index]["id"]): rows[index - 1]["level_percent"] for index in range(1, len(rows))}
    baseline_rows = [{"absolute_error_points": abs(float(row["observed_level_percent"]) - float(prior_by_id[str(row["target_estimate_id"])]))} for row in comparisons if str(row.get("target_estimate_id")) in prior_by_id]
    baseline = _metrics(baseline_rows)
    changed_ids = {str(rows[index]["id"]) for index in range(1, len(rows)) if abs(rows[index]["level_percent"] - rows[index - 1]["level_percent"]) >= 0.5}
    live_changed = sum(str(row.get("target_estimate_id")) in changed_ids and row.get("prediction_kind") == "live_shadow" for row in comparisons)
    live_ids = {str(row.get("target_estimate_id")) for row in comparisons if row.get("prediction_kind") == "live_shadow"}
    image_hashes = {str(row.get("image_sha256")) for row in rows if row.get("image_sha256")}
    live_image_hashes = {str(row.get("image_sha256")) for row in rows if str(row.get("id")) in live_ids and row.get("image_sha256")}
    jumps = sum(abs(rows[index]["level_percent"] - rows[index - 1]["level_percent"]) > 8 for index in range(1, len(rows)))
    raw_count = len(raw)
    quality = {
        "raw_observations": raw_count,
        "eligible_observations": len(rows),
        "excluded_or_duplicate_observations": max(0, raw_count - len(rows)),
        "large_change_events": jumps,
        "changed_observations": len(changed_ids),
        "live_changed_observations": live_changed,
        "unique_image_frames": len(image_hashes),
        "live_unique_image_frames": len(live_image_hashes),
        "repeated_image_observations": max(0, len(rows) - len(image_hashes)),
        "distinct_levels": len({round(row["level_percent"], 1) for row in rows}),
        "observed_level_values": sorted({round(row["level_percent"], 1) for row in rows}),
        "observed_level_min": round(min((row["level_percent"] for row in rows), default=0.0), 1),
        "observed_level_max": round(max((row["level_percent"] for row in rows), default=0.0), 1),
        "minimum_backfill_cases": MIN_BACKFILL_CASES,
        "minimum_live_cases": MIN_LIVE_CASES,
        "minimum_live_unique_frames": MIN_LIVE_UNIQUE_FRAMES,
        "minimum_changed_events": MIN_CHANGED_EVENTS,
        "minimum_live_changed_events": MIN_LIVE_CHANGED_EVENTS,
        "minimum_distinct_levels": MIN_DISTINCT_LEVELS,
        "accuracy_reference": "accepted future camera-AI estimates; not a calibrated physical gauge",
    }
    ready, issues = release_gate(backfill, live, quality)
    quality["release_issues"] = issues
    validation = {
        "method": "Strict historical walk-forward plus new forward/live shadow comparisons; no target uses future evidence.",
        "all_history": all_history,
        "last_value_baseline": baseline,
        "historical_backfill": backfill,
        "live_shadow": live,
        "release_mae_threshold_points": MAX_MAE_POINTS,
        "release_within_five_threshold_pct": MIN_WITHIN_FIVE_PCT,
        "eligible_for_use": ready,
    }
    parameters = {
        "estimator": "robust persistence plus shrunk recent median rate",
        "maximum_rate_points_per_hour": 0.75,
        "maximum_extrapolation_points": 5.0,
        "trend_shrinkage": 0.35,
        "jump_exclusion_points": 8.0,
    }
    current = fetch_one("SELECT id FROM cistern_learning_models WHERE estate_id=%s", (estate,)) or {}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cistern_learning_models "
            "(id,estate_id,model_version,model_status,trained_at,data_through,observation_count,backfill_case_count,live_case_count,parameters_snapshot,validation_metrics,data_quality_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE model_version=VALUES(model_version),model_status=VALUES(model_status),trained_at=VALUES(trained_at),data_through=VALUES(data_through),observation_count=VALUES(observation_count),backfill_case_count=VALUES(backfill_case_count),live_case_count=VALUES(live_case_count),parameters_snapshot=VALUES(parameters_snapshot),validation_metrics=VALUES(validation_metrics),data_quality_snapshot=VALUES(data_quality_snapshot)",
            (current.get("id") or new_id(), estate, MODEL_VERSION, "validated" if ready else "shadow_learning", generated_at,
             rows[-1]["observed_at"] if rows else None, len(rows), backfill["cases"], live["cases"],
             json.dumps(parameters), json.dumps(validation), json.dumps(quality)),
        )
    return cistern_learning_status()


def cistern_learning_status() -> dict[str, Any]:
    try:
        model = fetch_one("SELECT * FROM cistern_learning_models WHERE estate_id=%s", (estate_id(),)) or {}
    except Exception:
        return {}
    for key in ("parameters_snapshot", "validation_metrics", "data_quality_snapshot"):
        model[key] = _mapping(model.get(key))
    return json_ready(model)


def cistern_shadow_for_estimate(estimate_id: str | None) -> dict[str, Any]:
    if not estimate_id:
        return {"model": cistern_learning_status()}
    try:
        comparison = fetch_one(
            "SELECT prediction_kind,predicted_level_percent,observed_level_percent,absolute_error_points,evidence_through,prediction_for,horizon_minutes,model_version "
            "FROM cistern_shadow_predictions WHERE estate_id=%s AND target_estimate_id=%s ORDER BY generated_at DESC LIMIT 1",
            (estate_id(), estimate_id),
        ) or {}
    except Exception:
        comparison = {}
    return json_ready({"comparison": comparison, "model": cistern_learning_status()})
