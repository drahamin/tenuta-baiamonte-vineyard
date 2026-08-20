"""Pinned Fully Kiosk Browser installer and managed-device provisioning helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.error import URLError
import urllib.request


FULLY_KIOSK_VERSION = "1.61.2"
FULLY_KIOSK_FILENAME = f"Fully-Kiosk-Browser-v{FULLY_KIOSK_VERSION}-emm.apk"
FULLY_KIOSK_SOURCE_URL = (
    f"https://www.fully-kiosk.com/files/2026/08/{FULLY_KIOSK_FILENAME}"
)
FULLY_KIOSK_SHA256 = "87b970b14b12bfc696123bbd5ba60f151dd9804e401fc5645d8f73e34eddfa7d"
FULLY_KIOSK_PACKAGE_CHECKSUM = "h7lwsUsSv8aWEju9W6YPFR3ZgE5AH8VkXY9z407d-n0"
FULLY_KIOSK_DEVICE_ADMIN = "de.ozerov.fully/.DeviceOwnerReceiver"
FULLY_KIOSK_INSTALLER_PATH = Path(
    os.environ.get("FULLY_KIOSK_INSTALLER_PATH", f"/data/{FULLY_KIOSK_FILENAME}")
)


def installer_is_valid(path: Path = FULLY_KIOSK_INSTALLER_PATH) -> bool:
    """Return whether the locally cached APK is the pinned official build."""
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return False
    return hmac.compare_digest(digest, FULLY_KIOSK_SHA256)


def ensure_installer(path: Path = FULLY_KIOSK_INSTALLER_PATH) -> bool:
    """Download the official APK once and publish it only after checksum verification."""
    if installer_is_valid(path):
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        FULLY_KIOSK_SOURCE_URL,
        headers={"User-Agent": "Tenuta-Baiamonte-Vineyard/1.4.26"},
    )
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_name = temporary.name
            digest = hashlib.sha256()
            with urllib.request.urlopen(request, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    temporary.write(chunk)
        if not hmac.compare_digest(digest.hexdigest(), FULLY_KIOSK_SHA256):
            return False
        os.replace(temporary_name, path)
        os.chmod(path, 0o644)
        temporary_name = ""
        return True
    except (OSError, URLError):
        return False
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def settings_token(enrollment_key: str) -> str:
    """Create an unguessable, stable URL token without putting the key in the path."""
    digest = hmac.new(
        enrollment_key.encode("utf-8"),
        b"baiamonte-fully-settings-v1",
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def settings_token_is_valid(candidate: str, enrollment_key: str) -> bool:
    return bool(enrollment_key) and hmac.compare_digest(candidate, settings_token(enrollment_key))


def fully_settings(start_url: str, enrollment_key: str) -> dict[str, Any]:
    """Minimal one-page label profile, including boot and network recovery behavior."""
    return {
        "startURL": start_url,
        "authUsername": "baiamonte-enroll",
        "authPassword": enrollment_key,
        "launchOnBoot": True,
        "kioskMode": True,
        "kioskHomeStartURL": True,
        "setRemoveSystemUI": True,
        "showActionBar": False,
        "showAddressBar": False,
        "showNavigationBar": False,
        "showStatusBar": False,
        "showProgressBar": False,
        "keepScreenOn": True,
        "reloadOnWifiOn": True,
        "reloadOnInternet": True,
        "reloadOnScreenOn": True,
        "deleteCacheOnReload": False,
        "deleteWebstorageOnReload": False,
        "deleteCookiesOnReload": False,
        "enablePullToRefresh": False,
        "enableZoom": False,
        "webviewLongTap": False,
        "webviewOverscroll": False,
        "mdmDisableADB": True,
        "mdmDisableSafeModeBoot": True,
        "mdmDisableStatusBar": True,
        "mdmDisableUsbStorage": True,
        "mdmLockTask": True,
        "mdmLockTaskHomeButton": True,
        "mdmLockTaskOverviewButton": True,
        "mdmLockTaskNotifications": True,
        "mdmLockTaskGlobalActions": False,
        "mdmDisableScreenCapture": False,
        "remoteAdmin": True,
        "remoteAdminLan": True,
        "remoteAdminPassword": enrollment_key,
        "remoteAdminScreenshot": True,
        "remoteAdminFileManagement": False,
        "cloudService": False,
        "restartOnCrash": True,
        "restartAfterUpdate": True,
        "screenOrientation": "2",
    }


def provisioning_payload(origin: str, enrollment_key: str, timezone: str) -> dict[str, Any]:
    """Build the Android Enterprise QR payload for Fully Kiosk Browser EMM."""
    start_url = f"{origin}/enroll/$deviceID"
    token = settings_token(enrollment_key)
    return {
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": FULLY_KIOSK_DEVICE_ADMIN,
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": (
            f"{origin}/provision/{FULLY_KIOSK_FILENAME}"
        ),
        "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM": (
            FULLY_KIOSK_PACKAGE_CHECKSUM
        ),
        "android.app.extra.PROVISIONING_LOCALE": "it_IT",
        "android.app.extra.PROVISIONING_TIME_ZONE": timezone or "Europe/Rome",
        "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
        "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": False,
        "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
            "settingsUrl": f"{origin}/provision/{token}/fully-settings.json",
        },
    }


def provisioning_payload_json(origin: str, enrollment_key: str, timezone: str) -> str:
    return json.dumps(
        provisioning_payload(origin, enrollment_key, timezone),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
