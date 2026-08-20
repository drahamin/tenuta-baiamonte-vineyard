from pathlib import Path

from app.models import HarvestCreate


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_harvest_accepts_and_deduplicates_multiple_legal_parcels() -> None:
    payload = HarvestCreate.model_validate({
        "variety_id": "variety-1",
        "harvested_at": "2026-09-23T08:00:00",
        "weight_kg": 300,
        "parcel_ids": "parcel-1,parcel-2,parcel-1",
    })

    assert payload.parcel_ids == ["parcel-1", "parcel-2"]


def test_schema_preserves_many_parcels_per_pick() -> None:
    sql = read("db/migrations/077_harvest_parcel_traceability.sql")
    assert "CREATE TABLE IF NOT EXISTS harvest_lot_parcels" in sql
    assert "UNIQUE KEY uq_harvest_lot_parcel (harvest_lot_id, parcel_id)" in sql
    assert "FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(id) ON DELETE CASCADE" in sql
    assert "FOREIGN KEY (parcel_id) REFERENCES cadastral_parcels(id) ON DELETE RESTRICT" in sql


def test_harvest_form_and_transfer_keep_all_selected_parcels() -> None:
    frontend = read("app/static/app.js") + read("app/static/assets/cellar.js")
    api = read("app/main.py")
    assert "Legal parcels included in this pick" in frontend
    assert "data-harvest-parcel" in frontend
    assert "parcel_ids" in frontend
    assert "INSERT INTO harvest_lot_parcels" in api
    assert '"parcel_ids": [row["id"] for row in parcel_rows]' in api
    assert '"legal_parcels_carried_to_tank": len(parcel_rows)' in api
    assert "COALESCE(fruit_kg,0)+%s" in api
    assert "COALESCE(initial_l,0)+%s" in api


def test_every_tank_label_lists_combined_cadastral_provenance() -> None:
    service = read("app/tank_labels.py")
    label = read("app/static/assets/tank-label.js")
    css = read("app/static/assets/tank-label.css")
    assert "def legal_parcels_for_tank" in service
    assert "JOIN harvest_lot_parcels hp ON hp.harvest_lot_id=tr.harvest_lot_id" in service
    assert "SELECT DISTINCT p.id,p.municipality,p.cadastral_sheet,p.parcel_number" in service
    assert 'row["legal_parcels"] = legal_parcels_for_tank' in service
    assert "Particelle catastali" in label
    assert "parcel.legal_reference" in label
    assert "parcel.contract_protocol" in label
    assert "html.print-thermal .parcel-field" in css
