"""Apply the approved, one-time Garage camera assignment."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from app.ha_auth import home_assistant_token


HA_API = "http://supervisor/core/api"
DUPLICATE_CAMERA = "camera.east_360"


def _page_cameras(options: dict, page: int) -> list[str]:
    return [
        value.strip()
        for value in str(options.get(f"tv_camera_page_{page}_entities", "")).split(",")
        if value.strip()
    ]


def garage_rotation_update(options: dict, garage: str) -> dict | None:
    """Use a free Main slot or the East 360 slot already shown on another page."""
    if not options.get("tv_camera_pages_configured") or not options.get("tv_camera_page_3_enabled"):
        return None
    pages = [_page_cameras(options, page) for page in (1, 2, 3)]
    if any(garage in ids and options.get(f"tv_camera_page_{index}_enabled")
           for index, ids in enumerate(pages, start=1)):
        return {}
    main = pages[2]
    if len(main) < 6:
        main.append(garage)
    elif DUPLICATE_CAMERA in main and any(
        DUPLICATE_CAMERA in ids and options.get(f"tv_camera_page_{index}_enabled")
        for index, ids in enumerate(pages[:2], start=1)
    ):
        main[main.index(DUPLICATE_CAMERA)] = garage
    else:
        return None
    return {
        "tv_camera_page_3_entities": ",".join(main),
        "tv_camera_entities": ",".join(dict.fromkeys(entity for page in pages for entity in page)),
    }


def assign_garage_camera(data_dir: Path) -> None:
    """Save the rotation assignment after the Garage produces an image."""
    marker = data_dir / "garage-tv-rotation-v1.done"
    if marker.exists():
        return
    token = home_assistant_token()
    if not token:
        print("Garage TV rotation: Home Assistant authentication unavailable.", flush=True)
        return
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def request(path: str, payload: dict | None = None, timeout: int = 10) -> bytes:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(HA_API + path, headers=headers, data=data)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read(8 * 1024 * 1024)

    try:
        states = json.loads(request("/states"))
        garage = [
            row for row in states
            if row["entity_id"].startswith("camera.")
            and row["state"] not in {"unknown", "unavailable"}
            and row.get("attributes", {}).get("friendly_name", "").strip().casefold() == "garage"
            and row["attributes"].get("model") == "T817L"
        ]
        if len(garage) != 1:
            print("Garage TV rotation: Garage camera entity unavailable or ambiguous.", flush=True)
            return
        entity = garage[0]["entity_id"]
        if not garage[0]["attributes"].get("snapshot_available"):
            request("/services/eufy_security/capture_snapshot", {"entity_id": entity}, timeout=65)
        image = request(f"/camera_proxy/{entity}")
        if not (image.startswith(b"\xff\xd8\xff") and image.endswith(b"\xff\xd9")):
            print("Garage TV rotation: no verified JPEG from Home Assistant.", flush=True)
            return

        options = json.loads((data_dir / "options.json").read_text())
        runtime = data_dir / "runtime-options.json"
        overrides = json.loads(runtime.read_text()) if runtime.is_file() else {}
        updates = garage_rotation_update({**options, **overrides}, entity)
        if updates is None:
            print("Garage TV rotation: Main cameras has no free or duplicate slot.", flush=True)
            return
        if updates:
            temp = runtime.with_name("runtime-options.garage.tmp")
            with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
                json.dump({**overrides, **updates}, stream, indent=2, sort_keys=True)
            temp.replace(runtime)
        marker.touch()
        print(f"Garage TV rotation: verified a camera image and saved {entity}.", flush=True)
    except Exception as exc:
        print(f"Garage TV rotation: {type(exc).__name__}.", flush=True)
