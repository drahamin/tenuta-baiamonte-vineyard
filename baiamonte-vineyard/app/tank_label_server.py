from __future__ import annotations

import base64
import binascii
import html
import hmac
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .cellar_demo import apply_live_sensor_readings, live_sensor_entity_ids, live_sensor_tank_keys
from .config import get_settings
from .db import run_migrations
from .intelligence import home_assistant_state_map
from .tank_labels import kiosk_payload, request_kiosk_enrollment, tank_label_payload


ROOT = Path(__file__).resolve().parent
display_app = FastAPI(title="Baiamonte Cellar Labels", docs_url=None, redoc_url=None, openapi_url=None)
display_app.mount("/assets", StaticFiles(directory=ROOT / "static" / "assets"), name="assets")


@display_app.middleware("http")
async def protect_public_display_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/tank/", "/kiosk/", "/enroll/", "/api/")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@display_app.on_event("startup")
def startup() -> None:
    run_migrations()


@display_app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@display_app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /\n"


@display_app.get("/brand/logo.png")
def logo() -> FileResponse:
    return FileResponse(ROOT / "static" / "baiamonte-logo.png")


def _check_enrollment_key(authorization: str) -> None:
    expected = get_settings().cellar_label_enrollment_key.strip()
    if not expected:
        raise HTTPException(404, "Tablet enrollment is not configured")
    try:
        scheme, encoded = authorization.split(" ", 1)
        username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
    except (ValueError, UnicodeError, binascii.Error):
        username, password, scheme = "", "", ""
    if not (
        hmac.compare_digest(scheme.casefold(), "basic")
        and hmac.compare_digest(username, "baiamonte-enroll")
        and hmac.compare_digest(password, expected)
    ):
        raise HTTPException(
            401,
            "Valid tablet enrollment credentials required",
            headers={"WWW-Authenticate": 'Basic realm="Baiamonte display enrollment"'},
        )


def _enrollment_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


@display_app.get("/api/enroll/{device_key}")
def enrollment_data(device_key: str, authorization: str = Header(default="")) -> dict:
    _check_enrollment_key(authorization)
    try:
        return request_kiosk_enrollment(device_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@display_app.get("/enroll/{device_key}", response_class=HTMLResponse)
def enrollment_page(device_key: str, authorization: str = Header(default="")):
    _check_enrollment_key(authorization)
    try:
        data = request_kiosk_enrollment(device_key)
    except ValueError as exc:
        return HTMLResponse(_enrollment_page("Invalid device", str(exc), "———"), status_code=422, headers=_enrollment_headers())
    destination = data.get("destination_url") or data.get("kiosk_url")
    if data.get("status") == "approved" and destination:
        return RedirectResponse(destination, status_code=302, headers=_enrollment_headers())
    subtitle = data.get("message") or "Approve this display in Vineyard Operations"
    return HTMLResponse(
        _enrollment_page("Display enrollment", subtitle, str(data.get("pairing_code") or "———")),
        headers=_enrollment_headers(),
    )


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


def _enrollment_page(title: str, subtitle: str, pairing_code: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b0d0b"><meta name="referrer" content="no-referrer"><title>{html.escape(title)} · Baiamonte</title><link rel="stylesheet" href="/assets/tank-label.css"></head><body><main><header><img src="/brand/logo.png" alt="Tenuta Baiamonte"><div><p>DISPLAY · PROVISIONING</p><h1>{html.escape(title)}</h1><span>{html.escape(subtitle)}</span></div><i id="liveDot"></i></header><section class="legal-card enrollment-card"><div class="enrollment-panel"><small>Pairing code</small><div class="enrollment-code" id="pairingCode">{html.escape(pairing_code)}</div><p id="enrollmentStatus">Enter this code in Vineyard Operations</p></div></section><footer><span>Tenuta Baiamonte · Etna, Sicilia</span><span>Secure device enrollment</span></footer></main><script src="/assets/tank-enroll.js" defer></script></body></html>"""
