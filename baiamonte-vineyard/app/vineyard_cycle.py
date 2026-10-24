"""Season-aware context for the Today views.

The stage is intentionally derived from recorded harvest facts first and the
calendar second.  This keeps an older picking forecast from pulling the Today
page backwards after the fruit has actually been received.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def vineyard_year_stage(*, today: date, vintage_year: int, varieties: list[dict[str, Any]], harvested_kg: float = 0) -> dict[str, Any]:
    """Return a concise, presentation-safe vineyard stage and current focus."""
    def estate_actual(row: dict[str, Any]) -> float:
        field = "estate_harvested_kg" if "estate_harvested_kg" in row else "harvested_kg"
        return float(row.get(field) or 0)

    relevant = [row for row in varieties if float(row.get("planned_kg") or 0) > 0 or estate_actual(row) > 0]
    picked = [row for row in relevant if estate_actual(row) > 0]
    harvest_complete = bool(relevant) and len(picked) == len(relevant)
    harvest_days = [value for row in picked if (value := _day(row.get("last_pick_date")))]
    last_harvest = max(harvest_days, default=None)

    if vintage_year != today.year:
        code, name, next_stage = "historical", f"{vintage_year} vintage review", "Select the current year for today's vineyard stage"
        summary = "Recorded vintage facts are shown for review; live weather and estate systems remain current."
    elif harvest_complete and today.month in (8, 9, 10, 11):
        code, name, next_stage = "post_harvest", "Post-harvest recovery", "Leaf fall & dormancy"
        summary = "Harvest is recorded complete. Keep the vines supported through leaf fall while cellar work continues."
    elif today.month in (12, 1, 2):
        code, name, next_stage = "dormancy", "Dormancy & pruning preparation", "Pruning, then budbreak"
        summary = "Review vine balance and field condition, then schedule pruning against the approved agronomy plan."
    elif today.month in (3, 4):
        code, name, next_stage = "budbreak", "Budbreak & early shoot growth", "Canopy growth & flowering"
        summary = "Track phenology, early canopy development and weather-driven disease pressure."
    elif today.month in (5, 6):
        code, name, next_stage = "flowering", "Canopy growth & flowering", "Fruit set"
        summary = "Protect flowering, monitor canopy balance and record phenology by block."
    elif today.month == 7:
        code, name, next_stage = "fruit_set", "Fruit set & bunch development", "Veraison"
        summary = "Monitor water status, bunch development and canopy condition before ripening."
    elif today.month == 8:
        code, name, next_stage = "veraison", "Veraison & ripening", "Harvest readiness"
        summary = "Follow maturity samples, weather and variety-level readiness without replacing approved pick decisions."
    else:
        code, name, next_stage = "harvest", "Harvest readiness & picking", "Post-harvest recovery"
        summary = "Use actual picking records, maturity evidence and approved plans to coordinate the remaining harvest."

    if code == "post_harvest":
        focus = [
            {"label": "Vines", "title": "Support recovery", "detail": "Monitor canopy condition and soil moisture through leaf fall."},
            {"label": "Cellar", "title": "Follow the new vintage", "detail": "Keep fermentation, settling and scheduled checks current."},
            {"label": "Next", "title": next_stage, "detail": "Close vintage records and prepare pruning only after dormancy is established."},
        ]
    elif code == "dormancy":
        focus = [
            {"label": "Vines", "title": "Confirm dormancy", "detail": "Review wood maturity, vigor and block condition."},
            {"label": "Field", "title": "Prepare pruning", "detail": "Use the approved block plan and record completed work."},
            {"label": "Next", "title": next_stage, "detail": "Keep phenology and weather records ready for the new season."},
        ]
    elif code == "historical":
        focus = [
            {"label": "Vintage", "title": "Recorded facts", "detail": "Harvest and cellar figures belong to the selected year."},
            {"label": "Systems", "title": "Live now", "detail": "Weather, solar and equipment status remain current."},
            {"label": "Next", "title": "Return to current year", "detail": "Use the current vintage to see today's seasonal priorities."},
        ]
    else:
        focus = [
            {"label": "Vines", "title": name, "detail": summary},
            {"label": "Evidence", "title": "Record field observations", "detail": "Keep phenology, weather and completed work current."},
            {"label": "Next", "title": next_stage, "detail": "The Today page will advance when records and season timing do."},
        ]

    return {
        "code": code,
        "name": name,
        "summary": summary,
        "next_stage": next_stage,
        "focus": focus,
        "harvest_complete": harvest_complete,
        "harvested_kg": float(harvested_kg or 0),
        "last_harvest_date": last_harvest,
        "basis": "recorded harvest lots + vineyard calendar" if relevant else "vineyard calendar; harvest records not yet available",
    }
