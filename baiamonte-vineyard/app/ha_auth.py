"""Home Assistant authentication shared by the app and kiosk services."""

from __future__ import annotations

import os
from pathlib import Path


_TOKEN_FILES = (
    Path("/run/s6/container_environment/SUPERVISOR_TOKEN"),
    Path("/run/s6/container_environment/HASSIO_TOKEN"),
    Path("/var/run/s6/container_environment/SUPERVISOR_TOKEN"),
    Path("/var/run/s6/container_environment/HASSIO_TOKEN"),
)


def home_assistant_token() -> str:
    """Return the injected Home Assistant token without ever logging it.

    Current Supervisor versions inject ``SUPERVISOR_TOKEN``.  The additional
    fallbacks cover older installations and S6 environments where the token is
    materialized as a container-environment file instead of inherited by a
    child process.
    """
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        token = os.environ.get(name, "").strip().strip("\x00")
        if token:
            return token
    for path in _TOKEN_FILES:
        try:
            token = path.read_text(encoding="utf-8").strip().strip("\x00")
        except (OSError, UnicodeError):
            continue
        if token:
            return token
    return ""
