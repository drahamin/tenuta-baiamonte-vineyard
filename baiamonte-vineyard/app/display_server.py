"""LAN-only, read-only server for the 32-inch vineyard kiosk display."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .display_data import display_payload


static_dir = Path(__file__).resolve().parent / "static"
display_app = FastAPI(title="Tenuta Baiamonte Display", docs_url=None, redoc_url=None, openapi_url=None)


@display_app.get("/")
def display_home() -> FileResponse:
    return FileResponse(static_dir / "display.html", headers={"Cache-Control": "no-cache"})


@display_app.get("/display")
def display_alias() -> FileResponse:
    return display_home()


@display_app.get("/api/display-data")
def display_data() -> dict:
    return display_payload()


@display_app.get("/health")
def display_health() -> dict[str, bool]:
    return {"ok": True, "read_only": True}


display_app.mount("/assets", StaticFiles(directory=static_dir), name="display-assets")
