from pathlib import Path

from app import etna


ROOT = Path(__file__).resolve().parents[1]


def test_civil_protection_level_drives_the_normalized_etna_level(monkeypatch, tmp_path):
    civil_text = "The level of alert for Etna is orange. Operational phase: attention."

    def fake_fetch(url: str) -> str:
        if "bollettino" in url.lower() or "protezionecivile" in url.lower():
            return civil_text
        if "events" in url:
            return '{"features": []}'
        return "<html></html>"

    monkeypatch.setattr(etna, "_fetch", fake_fetch)
    monkeypatch.setattr(etna, "CACHE_PATH", tmp_path / "etna.json")
    monkeypatch.setattr(etna, "_cache", {})

    payload = etna.refresh_etna()

    civil = payload["civil_protection"]
    assert civil["published_level"] == "orange"
    assert civil["level"] == "orange"


def test_partial_etna_refresh_discloses_cached_sources(monkeypatch, tmp_path):
    prior = {
        "generated_at": "2026-08-19T10:00:00+00:00",
        "fresh": True,
        "civil_protection": {"level": "yellow"},
        "bulletin": {"summary": "prior bulletin"},
        "aviation": {"vaa": None},
        "earthquakes": [],
        "webcams": [],
    }

    def offline(_url: str) -> str:
        raise OSError("offline")

    monkeypatch.setattr(etna, "_fetch", offline)
    monkeypatch.setattr(etna, "CACHE_PATH", tmp_path / "etna.json")
    monkeypatch.setattr(etna, "_cache", prior)

    payload = etna.refresh_etna()

    assert payload["fresh"] is False
    assert payload["stale_sources"]
    assert payload["last_complete_at"] == prior["generated_at"]
    assert payload["civil_protection"] == prior["civil_protection"]


def test_trends_finance_is_gated_and_treatment_counts_are_explicit():
    source = (ROOT / "app" / "main.py").read_text()
    app_js = (ROOT / "app" / "static" / "assets" / "operations-enhancements.js").read_text()
    index = (ROOT / "app" / "static" / "index.html").read_text()

    assert "include_finance = has_finance_access" in source
    assert "record_type == \"historical_costs\" and not has_finance_access" in source
    assert "SUM(status='completed') treatments" in source
    assert "COUNT(*) treatment_records" in source
    assert "planned/other" in app_js
    assert 'value="expenses_eur" data-finance hidden' in index
    assert 'value="payments_eur" data-finance hidden' in index


def test_etna_ui_marks_partial_refreshes_as_cached():
    app_js = (ROOT / "app" / "static" / "assets" / "operations-enhancements.js").read_text()
    assert "PARTIAL UPDATE" in app_js
    assert "last complete" in app_js
    assert "stale_sources" in app_js


def test_history_chart_starts_at_zero_and_leaves_unrecorded_current_harvest_open():
    core_js = (ROOT / "app" / "static" / "app.js").read_text() + (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()
    operations_js = (ROOT / "app" / "static" / "assets" / "operations-enhancements.js").read_text()
    index = (ROOT / "app" / "static" / "index.html").read_text()
    assert "zeroBased=clean.some" in core_js
    assert "low=zeroBased?0" in core_js
    assert "measure==='harvest_kg'&&!Number(row.harvest_lots||0)" in operations_js
    assert "zeroBased:true" in operations_js
    assert "firstRecorded=values.findIndex" in operations_js
    assert "incomplete vintages remain open" in index


def test_2022_harvest_is_retained_only_as_rejected_evidence():
    migration = (ROOT / "db" / "migrations" / "070_reject_pre_operation_2022_harvest.sql").read_text()
    assert "vintage_year<2023" in migration
    assert "grapes_kg=NULL" in migration
    assert "wine_l=NULL" in migration
    assert "evidence_status='rejected_misattributed'" in migration
    assert "canonical_table=NULL" in migration
    assert "first harvest was 2023" in migration


def test_vintage_charts_begin_with_the_estates_first_2023_harvest():
    core_js = (ROOT / "app" / "static" / "app.js").read_text() + (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()
    operations_js = (ROOT / "app" / "static" / "assets" / "operations-enhancements.js").read_text()
    display_js = (ROOT / "app" / "static" / "display.js").read_text()
    assert "const firstEstateVintage=2023" in core_js
    assert ".filter(r=>Number(r.vintage_year)>=firstEstateVintage)" in core_js
    assert ".filter(row=>Number(row.vintage_year)>=firstEstateVintage)" in core_js
    assert "coverage.map(row=>Number(row.result_year)).filter(year=>year>=firstEstateVintage)" in core_js
    assert "visible.filter(row=>Number(row.year)>=firstEstateVintage)" in operations_js
    assert "(data.grapes.vintages||[]).filter(item=>Number(item.vintage_year)>=2023)" in display_js
    assert "const allRows=state.grapes?.variety_history||[],rows=allRows.filter" in core_js
    assert "latest=allRows.filter(row=>Number(row.vintage_year)===state.year)" in core_js
