from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .cellar_demo import apply_live_sensor_readings, live_sensor_entity_ids, live_sensor_tank_keys
from .config import get_settings
from .db import run_migrations
from .intelligence import home_assistant_state_map
from .tank_labels import kiosk_payload, tank_label_payload


ROOT = Path(__file__).resolve().parent
display_app = FastAPI(title="Baiamonte Cellar Labels", docs_url=None, redoc_url=None, openapi_url=None)
display_app.mount("/assets", StaticFiles(directory=ROOT / "static" / "assets"), name="assets")


@display_app.on_event("startup")
def startup() -> None:
    run_migrations()


@display_app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@display_app.get("/brand/logo.png")
def logo() -> FileResponse:
    return FileResponse(ROOT / "static" / "baiamonte-logo.png")


@display_app.get("/api/tank/{token}")
def tank_data(token: str) -> dict:
    data = _live_label(tank_label_payload(token))
    if not data:
        raise HTTPException(404, "Tank label not found")
    return data


@display_app.get("/tank/{token}", response_class=HTMLResponse)
def tank_page(token: str) -> HTMLResponse:
    data = _live_label(tank_label_payload(token))
    if not data:
        return HTMLResponse(_page("Tank label not found", "This label is not registered.", token, unavailable=True), status_code=404)
    if not data.get("available"):
        return HTMLResponse(_page("Tank retired", "No active contents. Historical records remain in Vineyard Operations.", token, unavailable=True), status_code=410)
    return HTMLResponse(_page(f"{data.get('code')} · {data.get('name')}", "Live cellar identification", token))


@display_app.get("/api/kiosk/{token}")
def kiosk_data(token: str) -> dict:
    data = kiosk_payload(token)
    if not data:
        raise HTTPException(404, "Tablet not found")
    if data.get("tank"):
        data["tank"] = _live_label(data["tank"])
        data["available"] = bool(data["tank"] and data["tank"].get("available"))
    return data


@display_app.get("/kiosk/{token}", response_class=HTMLResponse)
def kiosk_page(token: str) -> HTMLResponse:
    data = kiosk_payload(token)
    if not data:
        return HTMLResponse(_page("Tablet not found", "This tablet is not registered.", token, unavailable=True), status_code=404)
    if not data.get("available"):
        return HTMLResponse(_kiosk_page(data.get("kiosk", {}).get("name") or "Cellar tablet", token, assigned=False))
    tank = data.get("tank") or {}
    return HTMLResponse(_kiosk_page(f"{tank.get('code')} · {tank.get('name')}", token, assigned=True))


def _live_label(data: dict | None) -> dict | None:
    """Overlay only explicitly configured sensor-mode tanks; manual labels remain database authoritative."""
    if not data or data.get("reading_mode") != "sensor":
        return data
    settings = get_settings()
    keys = live_sensor_tank_keys(settings)
    configured = bool(
        data.get("sensor_entity_id")
        or str(data.get("code") or "").casefold() in keys
        or str(data.get("name") or "").casefold() in keys
    )
    data["sensor_configured"] = configured
    if not configured:
        data["sensor_status"] = "not_configured"
        return data
    try:
        apply_live_sensor_readings([data], settings, home_assistant_state_map(live_sensor_entity_ids(settings)))
        data["sensor_status"] = "fault" if data.get("sensor_issues") else "live"
    except Exception:
        # Keep the last authoritative database reading visible and disclose the stale/fault state.
        data["sensor_status"] = "fault"
    return data


def _page(title: str, subtitle: str, token: str, unavailable: bool = False) -> str:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    script = "" if unavailable else f'<script>window.BAIAMONTE_TANK_TOKEN={token!r}</script><script src="/assets/tank-label.js" defer></script>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b0d0b"><title>{safe_title} · Baiamonte</title><link rel="stylesheet" href="/assets/tank-label.css"></head><body class="{'unavailable' if unavailable else ''}"><main><header><img src="/brand/logo.png" alt="Tenuta Baiamonte"><div><p>CELLA · IDENTIFICAZIONE</p><h1 id="tankTitle">{safe_title}</h1><span id="tankSubtitle">{safe_subtitle}</span></div><i id="liveDot"></i></header><section id="labelBody" class="legal-card"><div class="offline-message">{safe_subtitle}</div></section><footer><span>Tenuta Baiamonte · Etna, Sicilia</span><time id="updatedAt"></time></footer></main>{script}</body></html>"""


def _kiosk_page(title: str, token: str, assigned: bool) -> str:
    safe_title = html.escape(title)
    subtitle = "Live cellar identification" if assigned else "No tank assigned. Assign this tablet in Vineyard Operations."
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b0d0b"><title>{safe_title} · Baiamonte</title><link rel="stylesheet" href="/assets/tank-label.css"></head><body><main><header><img src="/brand/logo.png" alt="Tenuta Baiamonte"><div><p>CELLA · IDENTIFICAZIONE</p><h1 id="tankTitle">{safe_title}</h1><span id="tankSubtitle">{html.escape(subtitle)}</span></div><i id="liveDot"></i></header><section id="labelBody" class="legal-card"><div class="offline-message">{html.escape(subtitle)}</div></section><footer><span>Tenuta Baiamonte · Etna, Sicilia</span><time id="updatedAt"></time></footer></main><script>window.BAIAMONTE_KIOSK_TOKEN={token!r}</script><script src="/assets/tank-label.js" defer></script></body></html>"""
