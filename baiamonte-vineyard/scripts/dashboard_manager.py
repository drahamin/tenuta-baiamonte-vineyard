"""Safely install the GitHub-managed Baiamonte dashboards."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request


SOURCE = Path(os.environ.get("BAIAMONTE_DASHBOARD_SOURCE", "/opt/baiamonte/dashboards"))
HA_CONFIG = Path(os.environ.get("BAIAMONTE_HA_CONFIG", "/homeassistant"))
DESTINATION = HA_CONFIG / "baiamonte_dashboards"
WWW_DESTINATION = HA_CONFIG / "www"
CONFIGURATION = HA_CONFIG / "configuration.yaml"
BEGIN = "# BEGIN TENUTA BAIAMONTE MANAGED DASHBOARDS"
END = "# END TENUTA BAIAMONTE MANAGED DASHBOARDS"

DASHBOARDS = {
    "vineyard-overview": {
        "filename": "baiamonte_dashboards/vineyard-overview.yaml",
        "title": "Vineyard Overview",
        "icon": "mdi:fruit-grapes",
        "show_in_sidebar": True,
        "require_admin": False,
    },
    "vineyard-display": {
        "filename": "baiamonte_dashboards/display-panel.yaml",
        "title": "Display Panel",
        "icon": "mdi:tablet-dashboard",
        "show_in_sidebar": False,
        "require_admin": False,
    },
    "vineyard-admin": {
        "filename": "baiamonte_dashboards/admin.yaml",
        "title": "Admin",
        "icon": "mdi:shield-crown-outline",
        "show_in_sidebar": True,
        "require_admin": True,
    },
}


def _yaml_bool(value: bool) -> str:
    return "true" if value else "false"


def _dashboard_entries(indent: int) -> list[str]:
    prefix = " " * indent
    lines = [f"{prefix}{BEGIN}\n"]
    for key, values in DASHBOARDS.items():
        lines.extend(
            [
                f"{prefix}{key}:\n",
                f"{prefix}  mode: yaml\n",
                f"{prefix}  filename: {values['filename']}\n",
                f"{prefix}  title: {values['title']}\n",
                f"{prefix}  icon: {values['icon']}\n",
                f"{prefix}  show_in_sidebar: {_yaml_bool(values['show_in_sidebar'])}\n",
                f"{prefix}  require_admin: {_yaml_bool(values['require_admin'])}\n",
            ]
        )
    lines.append(f"{prefix}{END}\n")
    return lines


def _remove_managed_block(lines: list[str]) -> list[str]:
    output: list[str] = []
    skipping = False
    for line in lines:
        if BEGIN in line:
            skipping = True
            continue
        if skipping and END in line:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return output


def _top_level_block_end(lines: list[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith((" ", "\t")):
            return index
    return len(lines)


def patch_configuration(text: str) -> tuple[str, str]:
    """Merge only the managed dashboard entries into configuration.yaml."""
    lines = _remove_managed_block(text.splitlines(keepends=True))
    lovelace_index = next(
        (i for i, line in enumerate(lines) if re.match(r"^lovelace:\s*(?:#.*)?$", line.rstrip("\n"))),
        None,
    )

    if lovelace_index is None:
        if any(re.match(r"^lovelace:\s*!include\b", line) for line in lines):
            return text, "skipped: configuration.yaml delegates lovelace to a separate include"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend(["lovelace:\n", "  dashboards:\n", *_dashboard_entries(4)])
        return "".join(lines), "registered a new lovelace dashboards section"

    block_end = _top_level_block_end(lines, lovelace_index)
    dashboards_index = next(
        (
            index
            for index in range(lovelace_index + 1, block_end)
            if re.match(r"^  dashboards:\s*(?:#.*)?$", lines[index].rstrip("\n"))
        ),
        None,
    )
    if dashboards_index is None:
        lines[lovelace_index + 1:lovelace_index + 1] = ["  dashboards:\n", *_dashboard_entries(4)]
        return "".join(lines), "added dashboards to the existing lovelace section"

    dashboards_end = block_end
    for index in range(dashboards_index + 1, block_end):
        line = lines[index]
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith("    "):
            dashboards_end = index
            break
    lines[dashboards_end:dashboards_end] = _dashboard_entries(4)
    return "".join(lines), "updated the existing lovelace dashboards section"


def _check_home_assistant_configuration() -> tuple[bool | None, str]:
    """Validate through Home Assistant Core's documented config-check API."""
    token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    if not token:
        return None, "Home Assistant API token unavailable; used structural validation"
    request = urllib.request.Request(
        "http://supervisor/core/api/config/core/check_config",
        data=b"{}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
        result = str(payload.get("result", "")).lower()
        detail = payload.get("errors") or payload.get("message") or f"result={result or 'unknown'}"
        return result == "valid", str(detail)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, str(exc)


def _structural_validation(text: str) -> tuple[bool, str]:
    """Verify the deterministic managed block before an API-level check."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return False, "managed dashboard markers are incomplete or duplicated"
    if text.index(BEGIN) >= text.index(END):
        return False, "managed dashboard markers are out of order"
    for key, values in DASHBOARDS.items():
        if f"    {key}:\n" not in text:
            return False, f"missing dashboard registration: {key}"
        if not (HA_CONFIG / values["filename"]).is_file():
            return False, f"missing dashboard file: {values['filename']}"
    patched_again, _ = patch_configuration(text)
    if patched_again != text:
        return False, "managed dashboard configuration is not idempotent"
    return True, "managed dashboard structure is complete"


def deploy_dashboards() -> None:
    """Copy dashboard sources, back up configuration, validate, and roll back on failure."""
    if not SOURCE.exists() or not HA_CONFIG.exists():
        print("Dashboard manager: source or Home Assistant configuration mount is unavailable.", flush=True)
        return

    DESTINATION.mkdir(parents=True, exist_ok=True)
    WWW_DESTINATION.mkdir(parents=True, exist_ok=True)
    logo_source = Path("/opt/baiamonte/app/static/baiamonte-logo.png")
    if logo_source.is_file():
        shutil.copy2(logo_source, WWW_DESTINATION / "baiamonte-logo.png")
        camera_cache = WWW_DESTINATION / "baiamonte-camera-cache"
        camera_cache.mkdir(parents=True, exist_ok=True)
        cistern_placeholder = camera_cache / "cistern-internal.jpg"
        if not cistern_placeholder.exists():
            shutil.copy2(logo_source, cistern_placeholder)
    previous_dashboards: dict[Path, bytes | None] = {}
    dashboards_changed = False
    for source in SOURCE.glob("*.yaml"):
        destination = DESTINATION / source.name
        source_bytes = source.read_bytes()
        existing_bytes = destination.read_bytes() if destination.exists() else None
        previous_dashboards[destination] = existing_bytes
        if existing_bytes == source_bytes:
            continue
        dashboards_changed = True
        temporary = destination.with_suffix(".yaml.new")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)

    if not CONFIGURATION.exists():
        print("Dashboard manager: dashboard files updated, but configuration.yaml was not found.", flush=True)
        return

    original = CONFIGURATION.read_text(encoding="utf-8")
    updated, message = patch_configuration(original)
    configuration_changed = updated != original
    if not configuration_changed and not dashboards_changed:
        print("Dashboard manager: managed dashboards are already current.", flush=True)
        return

    backup: Path | None = None
    if configuration_changed:
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = CONFIGURATION.with_name(f"configuration.yaml.baiamonte-{timestamp}.bak")
        shutil.copy2(CONFIGURATION, backup)
        temporary = CONFIGURATION.with_suffix(".yaml.new")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, CONFIGURATION)

    structurally_valid, structural_detail = _structural_validation(updated)
    valid, detail = _check_home_assistant_configuration() if structurally_valid else (False, structural_detail)
    if valid is False:
        if backup is not None:
            shutil.copy2(backup, CONFIGURATION)
        for destination, previous in previous_dashboards.items():
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                destination.write_bytes(previous)
        backup_detail = f" and restored {backup.name}" if backup is not None else ""
        print(
            f"Dashboard manager: validation failed; restored dashboard files{backup_detail}. Detail: {detail}",
            flush=True,
        )
        return
    validation_detail = detail if valid is None else "Home Assistant configuration check passed"
    backup_detail = f" Backup: {backup.name}." if backup is not None else ""
    print(
        f"Dashboard manager: dashboard files updated; {message}; {validation_detail}.{backup_detail}",
        flush=True,
    )
