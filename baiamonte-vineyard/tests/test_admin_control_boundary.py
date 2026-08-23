from datetime import datetime, timedelta
from pathlib import Path

from app.domains.admin_control import PROCESS_INTEGRATIONS, process_statuses
from app.main import app
from app.process_control import PROCESS_ORDER


ROOT = Path(__file__).resolve().parents[1]


def _controls() -> dict:
    return {
        "paused": False,
        "processes": {
            code: {"enabled": True, "interval_minutes": 15, "name": code}
            for code in PROCESS_ORDER
        },
    }


def test_admin_runtime_route_is_protected_and_existing_contract_remains() -> None:
    routes = {
        (route.path, tuple(sorted(route.methods or ()))): route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/admin/control")
    }
    assert ("/api/v1/admin/control", ("GET",)) in routes
    assert ("/api/v1/admin/control", ("PUT",)) in routes
    runtime = routes[("/api/v1/admin/control/runtime", ("GET",))]
    assert runtime.dependencies


def test_process_health_is_pure_and_preserves_admin_states() -> None:
    now = datetime(2026, 8, 23, 12, 0)
    latest = {
        PROCESS_INTEGRATIONS["weather"]: {"status": "processed", "occurred_at": now - timedelta(minutes=2)},
        PROCESS_INTEGRATIONS["gmail"]: {"status": "failed", "occurred_at": now - timedelta(minutes=2), "error_message": "mail down"},
    }
    rows = process_statuses(
        _controls(),
        latest,
        {"jobs": [{"code": "forecast_sources", "state": "running"}, {"code": "cistern", "state": "timed_out"}]},
        now,
    )
    by_code = {row["code"]: row for row in rows}
    assert by_code["weather"]["health"] == "healthy"
    assert by_code["gmail"]["health"] == "error"
    assert by_code["gmail"]["last_error"] == "mail down"
    assert by_code["forecast_sources"]["health"] == "running"
    assert by_code["cistern"]["health"] == "timed_out"
    assert by_code["public_feed"]["health"] == "waiting"


def test_main_delegates_admin_foundation_and_keeps_people_assembly_separate() -> None:
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    service = (ROOT / "app" / "domains" / "admin_control.py").read_text(encoding="utf-8")
    handler = source.split("def admin_control(request: Request)", 1)[1].split(
        "@app.put(\"/api/v1/admin/people/{person_entity:path}/profile\"", 1
    )[0]
    assert "admin_control_foundation(APP_STARTED_MONOTONIC)" in handler
    assert "FROM integration_events current_event" not in handler
    assert "def process_statuses(" in service
    assert "people_directory" in handler
    assert "people_directory" not in service
