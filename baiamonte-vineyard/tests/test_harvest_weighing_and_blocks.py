from pathlib import Path

from app.models import HarvestCreate, HarvestWineryWeightUpdate


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_net_weight_per_crate_calculates_field_total_and_deduplicates_blocks() -> None:
    payload = HarvestCreate.model_validate({
        "variety_id": "variety-1",
        "harvested_at": "2026-09-23T08:00:00",
        "net_kg_per_crate": 14.75,
        "crate_count": 20,
        "block_ids": "block-1,block-2,block-1",
    })

    assert payload.block_ids == ["block-1", "block-2"]
    assert payload.block_id == "block-1"
    assert payload.gross_kg == 295
    assert payload.weight_kg == 295


def test_winery_weight_is_a_valid_second_authoritative_weight() -> None:
    payload = HarvestWineryWeightUpdate.model_validate({"winery_weight_kg": 291.4, "notes": "Winery scale"})
    assert payload.winery_weight_kg == 291.4


def test_harvest_schema_and_route_preserve_both_weight_stages() -> None:
    migration = read("db/migrations/112_harvest_field_and_winery_weights.sql")
    route = read("app/domains/harvest_routes.py")
    assert "CREATE TABLE IF NOT EXISTS harvest_lot_blocks" in migration
    assert "field_weight_kg" in migration
    assert "winery_weight_kg" in migration
    assert 'router.patch("/{harvest_id}/winery-weight"' in route
    assert "request_harvest_refresh" in route


def test_harvest_tablet_form_is_multi_block_scroll_safe_and_reconciliable() -> None:
    frontend = read("app/static/assets/harvest.js")
    css = read("app/static/app.css")
    assert "Net kg per crate" in frontend
    assert "data-harvest-block" in frontend
    assert "Calculated total gross kg" in frontend
    assert "Winery second weight" in frontend
    assert "harvest_winery_weight" not in frontend
    assert ".harvest-extra-fields" in css
    assert "#entryDialog #entryForm" in css
