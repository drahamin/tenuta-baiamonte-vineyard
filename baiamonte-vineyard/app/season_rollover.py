"""Idempotent January 1 bootstrap for a new vineyard vintage."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .db import transaction
from .estate_time import estate_year
from .service import estate_id, season_for_year


logger = logging.getLogger("baiamonte")
ROLLOVER_SETTING = "annual_season_rollover"


def ensure_annual_rollover(year: int | None = None) -> dict[str, Any]:
    """Create only new-season planning records; never copy prior actual work."""
    selected_year = int(year or estate_year())
    selected_season = season_for_year(selected_year)
    counts: dict[str, int] = {}
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key=%s FOR UPDATE",
            (estate_id(), ROLLOVER_SETTING),
        )
        marker = cursor.fetchone() or {}
        raw_marker = marker.get("setting_value") or {}
        if isinstance(raw_marker, str):
            try:
                raw_marker = json.loads(raw_marker)
            except (TypeError, ValueError):
                raw_marker = {}
        previously_processed = int((raw_marker or {}).get("vintage_year") or 0)

        cursor.execute(
            "UPDATE seasons SET status='cellar' WHERE estate_id=%s AND vintage_year=%s "
            "AND status IN ('active','harvest')",
            (estate_id(), selected_year - 1),
        )
        counts["prior_seasons_advanced"] = cursor.rowcount
        cursor.execute(
            "UPDATE seasons SET status='active' WHERE id=%s AND status='planning'",
            (selected_season,),
        )
        counts["current_season_activated"] = cursor.rowcount

        # Carry operational constants forward, not measurements or completed work.
        cursor.execute(
            "INSERT IGNORE INTO varietal_program_settings "
            "(id,estate_id,vintage_year,nerello_variety_name,grenache_variety_name,grecanico_variety_name,"
            "crate_weight_kg,expected_yield_l_per_kg,tank_working_fill_pct,updated_by) "
            "SELECT UUID(),estate_id,%s,nerello_variety_name,grenache_variety_name,grecanico_variety_name,"
            "crate_weight_kg,expected_yield_l_per_kg,tank_working_fill_pct,'annual-season-rollover' "
            "FROM varietal_program_settings WHERE estate_id=%s AND vintage_year<%s "
            "ORDER BY vintage_year DESC LIMIT 1",
            (selected_year, estate_id(), selected_year),
        )
        counts["program_settings_created"] = cursor.rowcount
        if not counts["program_settings_created"]:
            cursor.execute(
                "INSERT IGNORE INTO varietal_program_settings (id,estate_id,vintage_year,updated_by) "
                "VALUES (UUID(),%s,%s,'annual-season-rollover-default')",
                (estate_id(), selected_year),
            )
            counts["program_settings_created"] = cursor.rowcount

        # Long-range projections normally already contain the new vintage. If a
        # future boundary exceeds the modeled horizon, retain the latest baseline
        # explicitly as provisional input until the learned forecast is refreshed.
        cursor.execute(
            "INSERT IGNORE INTO production_forecasts "
            "(estate_id,vintage_year,scenario,variety_name,grape_kg,crates_15kg,source,notes) "
            "SELECT p.estate_id,%s,p.scenario,p.variety_name,p.grape_kg,p.crates_15kg,"
            "'annual rollover baseline',CONCAT('Carried from ',p.vintage_year,"
            "' until current-season agronomy and yield evidence recalibrates the forecast.') "
            "FROM production_forecasts p JOIN (SELECT variety_name,scenario,MAX(vintage_year) vintage_year "
            "FROM production_forecasts WHERE estate_id=%s AND vintage_year<%s GROUP BY variety_name,scenario) latest "
            "ON latest.variety_name=p.variety_name AND latest.scenario=p.scenario AND latest.vintage_year=p.vintage_year "
            "WHERE p.estate_id=%s AND p.scenario='base'",
            (selected_year, estate_id(), selected_year, estate_id()),
        )
        counts["forecast_rows_created"] = cursor.rowcount

        cursor.execute(
            "INSERT IGNORE INTO grape_allocation_plans "
            "(estate_id,vintage_year,grape_name,total_kg,total_crates_15kg,wine_destination,"
            "blend_kg,blend_crates_15kg,varietal_kg,varietal_crates_15kg,field_instruction,source) "
            "SELECT p.estate_id,p.vintage_year,p.variety_name,p.grape_kg,p.crates_15kg,"
            "CONCAT(p.variety_name,' · 100%% varietal'),0,0,p.grape_kg,p.crates_15kg,"
            "CONCAT('Pick, identify and vinify ',p.variety_name,' separately.'),'annual season rollover' "
            "FROM production_forecasts p WHERE p.estate_id=%s AND p.vintage_year=%s AND p.scenario='base'",
            (estate_id(), selected_year),
        )
        counts["allocation_rows_created"] = cursor.rowcount

        cursor.execute(
            "INSERT IGNORE INTO wine_output_plans "
            "(estate_id,vintage_year,finished_wine,composition,grape_kg,wine_l,bottles_750ml,source) "
            "SELECT p.estate_id,p.vintage_year,p.variety_name,CONCAT('100%% ',p.variety_name),p.grape_kg,"
            "ROUND(p.grape_kg*s.expected_yield_l_per_kg,3),"
            "FLOOR(p.grape_kg*s.expected_yield_l_per_kg/0.75),'annual season rollover' "
            "FROM production_forecasts p JOIN varietal_program_settings s "
            "ON s.estate_id=p.estate_id AND s.vintage_year=p.vintage_year "
            "WHERE p.estate_id=%s AND p.vintage_year=%s AND p.scenario='base'",
            (estate_id(), selected_year),
        )
        counts["wine_output_rows_created"] = cursor.rowcount

        marker_value = json.dumps({
            "vintage_year": selected_year,
            "season_id": selected_season,
            "policy": "planning records only; prior-year actuals remain historical",
        })
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), ROLLOVER_SETTING, marker_value),
        )
    return {
        "vintage_year": selected_year,
        "season_id": selected_season,
        "year_advanced": previously_processed != selected_year,
        **counts,
    }


async def season_rollover_loop(initial: dict[str, Any] | None = None) -> None:
    """Notice a Rome-calendar year change without requiring an app restart."""
    result = initial
    last_year: int | None = None
    while True:
        current_year = estate_year()
        if result is None or current_year != last_year:
            try:
                result = result or await asyncio.to_thread(ensure_annual_rollover, current_year)
                if result.get("year_advanced"):
                    from .display_data import clear_display_cache
                    from .intelligence import refresh_harvest_projections

                    clear_display_cache()
                    await asyncio.to_thread(refresh_harvest_projections)
                logger.info("Season rollover ready: %s", result)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Could not initialize vineyard season %s", current_year)
            finally:
                result = None
                last_year = current_year
        await asyncio.sleep(60)
