from datetime import date, datetime
from pathlib import Path

from app import service
from app.process_control import PROCESS_ORDER, process_controls


ROOT = Path(__file__).resolve().parents[1]


def test_harvest_projection_is_a_first_class_scheduled_process(monkeypatch) -> None:
    class Settings:
        full_refresh_minutes = 60
        planning_sync_minutes = 15
        weather_sync_minutes = 15
        cistern_level_ai_enabled = True
        gmail_address = ""
        gmail_app_password = ""
        gmail_poll_minutes = 15
        whatsapp_access_token = ""
        whatsapp_test_access_token = ""
        whatsapp_phone_number_id = ""
        whatsapp_test_phone_number_id = ""
        fattureincloud_token = ""
        fattureincloud_company_id = ""
        fattureincloud_sync_minutes = 360
        etna_enabled = True
        etna_refresh_minutes = 5
        public_publish_url = "https://example.invalid/feed"
        public_publish_minutes = 15

    import app.process_control as control

    monkeypatch.setattr(control, "get_settings", lambda: Settings())
    monkeypatch.setattr(control, "fetch_one", lambda *args, **kwargs: None)
    controls = process_controls()
    assert PROCESS_ORDER.index("weather") < PROCESS_ORDER.index("harvest") < PROCESS_ORDER.index("planning") < PROCESS_ORDER.index("public_feed")
    assert controls["processes"]["harvest"]["enabled"] is True
    assert controls["processes"]["harvest"]["interval_minutes"] == 30


def test_scheduler_and_admin_mapping_use_one_harvest_job() -> None:
    intelligence = (ROOT / "app" / "intelligence.py").read_text()
    main = (ROOT / "app" / "main.py").read_text()
    assert '"harvest": ("harvest-projection", refresh_harvest_projections)' in intelligence
    assert '"harvest": "harvest-projection"' in intelligence
    assert '"harvest": "harvest-projection"' in main
    assert intelligence.index('jobs.append(("home-assistant-weather"') < intelligence.index('jobs.append(("harvest-projection"') < intelligence.index('jobs.append(("google-planning"')


def test_public_website_prefers_human_plan_over_model(monkeypatch) -> None:
    def fake_fetch_one(query, params):
        if "FROM estates" in query:
            return {"slug": "baiamonte", "name": "Tenuta Baiamonte", "timezone": "Europe/Rome", "total_area_ha": 6}
        if "FROM weather_observations" in query:
            return {"observed_at": datetime(2026, 8, 17, 10), "temp_c": 28}
        if "FROM vineyard_blocks" in query:
            return {"vineyard_area_ha": 6, "vine_count": 10000, "block_count": 5}
        raise AssertionError(query)

    def fake_fetch_all(query, params):
        if "FROM v_harvest_summary" in query and "SELECT vintage_year" in query:
            return []
        if "FROM grape_varieties" in query:
            return [
                {
                    "variety": "Grecanico", "plan_date": date(2026, 9, 8), "status": "confirmed", "approved_by": None,
                    "plan_confidence": "high", "forecast_method": "field decision", "plan_updated_at": datetime(2026, 8, 17, 9),
                    "final_forecast_date": date(2026, 9, 3), "gdd_predicted_date": date(2026, 9, 4),
                    "forecast_confidence": "medium", "forecast_updated_at": datetime(2026, 8, 17, 10),
                    "first_pick_date": None, "last_pick_date": None, "total_kg": None, "total_crates": None, "lot_count": 0,
                },
                {
                    "variety": "Nerello", "plan_date": date(2026, 9, 20), "status": "provisional", "approved_by": None,
                    "plan_confidence": "low", "forecast_method": "scheduled", "plan_updated_at": datetime(2026, 8, 17, 9),
                    "final_forecast_date": date(2026, 9, 17), "gdd_predicted_date": date(2026, 9, 18),
                    "forecast_confidence": "medium", "forecast_updated_at": datetime(2026, 8, 17, 10),
                    "first_pick_date": None, "last_pick_date": None, "total_kg": None, "total_crates": None, "lot_count": 0,
                },
            ]
        raise AssertionError(query)

    monkeypatch.setattr(service, "estate_id", lambda: "estate")
    monkeypatch.setattr(service, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(service, "fetch_all", fake_fetch_all)
    feed = service.public_harvest_feed()
    by_name = {item["variety"]: item for item in feed["items"]}
    assert feed["schema_version"] == 3
    assert by_name["Grecanico"]["predicted_date"] == "2026-09-08"
    assert by_name["Grecanico"]["date_source"] == "confirmed_plan"
    assert by_name["Grecanico"]["human_approval_required"] is False
    assert by_name["Nerello"]["predicted_date"] == "2026-09-17"
    assert by_name["Nerello"]["date_source"] == "scheduled_forecast"
    assert by_name["Nerello"]["human_approval_required"] is True
