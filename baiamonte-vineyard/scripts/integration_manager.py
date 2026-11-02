"""Install GitHub-managed Baiamonte Home Assistant custom integrations."""

from __future__ import annotations

import base64
import datetime as dt
import filecmp
import json
import os
from pathlib import Path
import re
import secrets
import shutil


SOURCE = Path(os.environ.get("BAIAMONTE_INTEGRATION_SOURCE", "/opt/baiamonte/custom_components"))
APP_SOURCE = Path(os.environ.get("BAIAMONTE_APP_SOURCE", "/opt/baiamonte/app"))
HA_CONFIG = Path(os.environ.get("BAIAMONTE_HA_CONFIG", "/homeassistant"))
DESTINATION = HA_CONFIG / "custom_components"
BACKUPS = HA_CONFIG / ".baiamonte-integration-backups"
BRANDING_MARKER = "# Managed by Baiamonte Vineyard: branded login"


def deploy_mobile_gateway_runtime(values: dict, ha_config: Path = HA_CONFIG) -> bool:
    """Atomically hand the narrow relay settings to Core without YAML secrets."""
    target = ha_config / ".storage" / "baiamonte_mobile_gateway.json"
    requested = values.get("mobile_site_gateway_enabled") is True
    secret = str(values.get("mobile_site_exchange_hmac_key") or "").strip()
    valid_secret = False
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        try:
            valid_secret = len(base64.urlsafe_b64decode(secret + "=")) == 32
        except (ValueError, TypeError):
            valid_secret = False
    enabled = requested and valid_secret
    payload = {
        "enabled": enabled,
        "public_host": "baiamonte.rhmproxy.com",
        "target_origin": "http://0c04eef6-baiamonte-vineyard:8099",
        "exchange_hmac_key": secret if enabled else "",
    }
    serialized = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and not target.is_symlink() and target.read_bytes() == serialized:
            os.chmod(target, 0o600)
            return False
        temporary = target.with_name(f".{target.name}.new-{os.getpid()}-{secrets.token_hex(6)}")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            os.write(descriptor, serialized)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except OSError as error:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        print(f"Mobile gateway runtime handoff failed closed: {type(error).__name__}", flush=True)
        return False
    if requested and not enabled:
        print("Mobile gateway remains disabled: a valid 256-bit exchange key is required.", flush=True)
    return True


def _deploy_branding_assets() -> bool:
    """Install login artwork where unauthenticated Home Assistant can serve it."""
    logo_source = APP_SOURCE / "static" / "baiamonte-logo.png"
    icon_source = APP_SOURCE / "static" / "icon.png"
    if not logo_source.is_file() or not icon_source.is_file():
        return False
    destination = HA_CONFIG / "www" / "baiamonte-branding"
    destination.mkdir(parents=True, exist_ok=True)
    changed = False
    for name, source in (("logon-logo.png", logo_source), ("favicon.png", icon_source), ("apple-touch-icon.png", icon_source)):
        target = destination / name
        if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
            shutil.copy2(source, target)
            changed = True
    return changed


def _enable_branding_in_yaml() -> bool:
    """Enable the packaged integration without disturbing existing YAML."""
    configuration = HA_CONFIG / "configuration.yaml"
    if not configuration.is_file():
        return False
    original = configuration.read_text(encoding="utf-8")
    if re.search(r"(?m)^baiamonte_branding\s*:", original):
        return False
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(configuration, BACKUPS / f"configuration-{timestamp}.yaml")
    separator = "" if original.endswith("\n") else "\n"
    configuration.write_text(
        f"{original}{separator}\n{BRANDING_MARKER}\nbaiamonte_branding:\n",
        encoding="utf-8",
    )
    return True


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
    assets_changed = _deploy_branding_assets()
    yaml_changed = _enable_branding_in_yaml()
    if assets_changed or yaml_changed:
        print(
            "Integration manager: installed Baiamonte login assets and enabled guarded branding. "
            "Restart Home Assistant Core once to apply it.",
            flush=True,
        )
