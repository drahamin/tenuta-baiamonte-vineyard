"""Variety-specific grape-to-liquid yield profiles for planning and reconciliation."""

from __future__ import annotations

import re
from typing import Any


def variety_key(value: Any) -> str:
    """Normalize operational synonyms without changing the legal display name."""
    name = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    if "alicante" in name or "grenache" in name or "granache" in name:
        return "grenache"
    if "nerello" in name or "narello" in name:
        return "nerello mascalese"
    if "grecanico" in name:
        return "grecanico"
    return name


def is_blended_summary(value: Any) -> bool:
    """Return whether a historical summary represents a multi-variety wine."""
    name = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    return "blend" in name or "mamma fiamma" in name or ("grenache" in name and "nerello" in name)


def build_varietal_yield_profiles(
    year: int,
    historical_rows: list[dict[str, Any]],
    fruit_rows: list[dict[str, Any]],
    liquid_rows: list[dict[str, Any]],
    *,
    fallback_l_per_kg: float,
    overrides: dict[str, float] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build predictive and current observed ratios without mixing their evidence.

    Predictive ratios use only reconciled prior-vintage variety summaries. Current
    cellar liquid is shown as an observed ratio, but is never fed back into the
    prediction until the vintage has a reconciled summary.
    """
    overrides = {variety_key(key): float(value) for key, value in (overrides or {}).items() if value}
    history: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for row in historical_rows:
        vintage = int(row.get("vintage_year") or 0)
        name = str(row.get("variety_name") or "").strip()
        if is_blended_summary(name):
            continue
        key = variety_key(name)
        grapes = float(row.get("grapes_kg") or 0)
        wine = float(row.get("wine_l") or 0)
        evidence = str(row.get("evidence_status") or "").casefold()
        note = str(row.get("reconciliation_note") or "").casefold()
        if not key or key in {"total", "vintage total", "totale vendemmia"} or vintage >= year:
            continue
        if grapes <= 0 or wine <= 0 or "reported - review" in evidence or "use cautiously" in note or "unusually high" in note:
            continue
        labels.setdefault(key, name)
        history.setdefault(key, []).append({"vintage_year": vintage, "grapes_kg": grapes, "wine_l": wine})

    fruit: dict[str, dict[str, float]] = {}
    for row in fruit_rows:
        key = variety_key(row.get("variety_name"))
        if not key:
            continue
        labels.setdefault(key, str(row.get("variety_name") or key).strip())
        item = fruit.setdefault(key, {"received": 0.0, "estate": 0.0, "purchased": 0.0})
        item["received"] += float(row.get("fruit_kg") or row.get("recorded_grape_kg") or row.get("grape_kg") or 0)
        item["estate"] += float(row.get("estate_fruit_kg", row.get("estate_grape_kg")) or 0)
        item["purchased"] += float(row.get("purchased_fruit_kg", row.get("purchased_grape_kg")) or 0)

    liquid: dict[str, dict[str, float]] = {}
    for row in liquid_rows:
        key = variety_key(row.get("variety_name"))
        if not key:
            continue
        labels.setdefault(key, str(row.get("variety_name") or key).strip())
        item = liquid.setdefault(key, {"current": 0.0, "initial": 0.0})
        item["current"] += float(row.get("measured_wine_l", row.get("current_liquid_l")) or 0)
        item["initial"] += float(row.get("initial_liquid_l") or 0)

    keys = set(labels) | set(history) | set(fruit) | set(liquid) | set(overrides)
    profiles: dict[str, dict[str, Any]] = {}
    for key in sorted(keys):
        observations = history.get(key, [])
        historical_kg = sum(row["grapes_kg"] for row in observations)
        historical_l = sum(row["wine_l"] for row in observations)
        learned = historical_l / historical_kg if historical_kg else float(fallback_l_per_kg)
        configured = key in overrides
        prediction = overrides.get(key, learned)
        received = fruit.get(key, {}).get("received", 0.0)
        current = liquid.get(key, {}).get("current", 0.0)
        initial = liquid.get(key, {}).get("initial", 0.0)
        source = "Enologist per-variety override" if configured else (
            "Weighted reconciled prior-vintage ratio for this variety" if observations else
            "Estate-wide fallback; no reconciled prior-vintage variety ratio"
        )
        profiles[key] = {
            "variety_key": key,
            "variety_name": labels.get(key) or key.title(),
            "predictive_l_per_kg": round(prediction, 6),
            "predictive_kg_per_l": round(1 / prediction, 6) if prediction > 0 else None,
            "prediction_source": source,
            "prediction_is_configured": configured,
            "historical_vintage_count": len(observations),
            "historical_vintages": [row["vintage_year"] for row in observations],
            "historical_grapes_kg": round(historical_kg, 3),
            "historical_finished_wine_l": round(historical_l, 3),
            "historical_results": [{
                "vintage_year": row["vintage_year"],
                "grapes_kg": round(row["grapes_kg"], 3),
                "finished_wine_l": round(row["wine_l"], 3),
                "observed_l_per_kg": round(row["wine_l"] / row["grapes_kg"], 6),
                "full_bottles_750ml": int(row["wine_l"] / 0.75),
            } for row in observations],
            "confidence": "medium" if len(observations) >= 3 else "low",
            "received_grapes_kg": round(received, 3),
            "current_measured_liquid_l": round(current, 3),
            "initial_measured_liquid_l": round(initial, 3),
            "current_observed_l_per_kg": round(current / received, 6) if received > 0 and current > 0 else None,
            "initial_observed_l_per_kg": round(initial / received, 6) if received > 0 and initial > 0 else None,
            "predicted_l_from_received_grapes": round(received * prediction, 3),
            "predicted_full_bottles_from_received_grapes": int(received * prediction / 0.75),
        }
    return profiles
