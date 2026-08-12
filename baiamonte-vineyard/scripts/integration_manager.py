"""Install GitHub-managed Baiamonte Home Assistant custom integrations."""

from __future__ import annotations

import datetime as dt
import filecmp
import os
from pathlib import Path
import shutil


SOURCE = Path(os.environ.get("BAIAMONTE_INTEGRATION_SOURCE", "/opt/baiamonte/custom_components"))
HA_CONFIG = Path(os.environ.get("BAIAMONTE_HA_CONFIG", "/homeassistant"))
DESTINATION = HA_CONFIG / "custom_components"
BACKUPS = HA_CONFIG / ".baiamonte-integration-backups"


def _same_tree(source: Path, destination: Path) -> bool:
    if not destination.is_dir():
        return False
    source_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    destination_files = {path.relative_to(destination) for path in destination.rglob("*") if path.is_file()}
    if source_files != destination_files:
        return False
    return all(filecmp.cmp(source / path, destination / path, shallow=False) for path in source_files)


def deploy_integrations() -> None:
    """Install each packaged custom integration and retain a recoverable backup."""
    if not SOURCE.is_dir() or not HA_CONFIG.is_dir():
        print("Integration manager: source or Home Assistant configuration mount is unavailable.", flush=True)
        return
    DESTINATION.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    for source in SOURCE.iterdir():
        if not source.is_dir() or not (source / "manifest.json").is_file():
            continue
        destination = DESTINATION / source.name
        if _same_tree(source, destination):
            continue
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
        temporary = DESTINATION / f".{source.name}.new-{timestamp}"
        shutil.copytree(source, temporary)
        if destination.exists():
            BACKUPS.mkdir(parents=True, exist_ok=True)
            destination.rename(BACKUPS / f"{source.name}-{timestamp}")
        temporary.rename(destination)
        changed.append(source.name)
    if changed:
        print(
            "Integration manager: installed " + ", ".join(changed) + ". Restart Home Assistant Core once to load it.",
            flush=True,
        )
    else:
        print("Integration manager: managed integrations are already current.", flush=True)
