"""Apply the Mobile Safari-tested Tenuta Baiamonte login treatment."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .brander import BrandingError, apply_branding, restore_vendor_page
from .label_proxy import BaiamonteLabelProxyView
from .mcp_proxy import BaiamonteMcpProxyView

DOMAIN = "baiamonte_branding"
_LOGGER = logging.getLogger(__name__)
# Use the add-on's deliberately read-only display feed.  The operations status
# endpoint on 8099 requires a signed-in user/API key and therefore correctly
# returns 401 to Home Assistant during startup.  Port 8101 is the same bounded
# feed used by estate TVs and is safe for the local dashboard integration.
_DEFAULT_STATUS_URL = "http://192.168.0.10:8101/api/display-data"
_CISTERN_REFRESH_INTERVAL = timedelta(minutes=2)


def _cistern_attributes(level: dict[str, Any]) -> dict[str, Any]:
    """Return safe attributes shared by the durable cistern entities."""
    return {
        "source": level.get("source") or "vineyard_operations",
        "estimate": True,
        "confidence": level.get("confidence"),
        "observed_at": level.get("observed_at"),
        "notes": level.get("notes"),
    }


async def _async_refresh_cistern_entities(hass: HomeAssistant, status_url: str) -> None:
    """Keep dashboard entities present across Core and app restarts.

    The vineyard app still publishes accepted readings immediately.  This local
    poll is the durable owner that recreates the two Lovelace entities whenever
    Home Assistant starts, even if the app is still warming up.
    """
    level: dict[str, Any] = {}
    try:
        session = async_get_clientsession(hass)
        async with session.get(status_url, timeout=ClientTimeout(total=15)) as response:
            response.raise_for_status()
            payload = await response.json()
            level = payload.get("cistern_level") or (payload.get("system_status") or {}).get("cistern_level") or {}
    except (ClientError, TimeoutError, ValueError, TypeError) as error:
        _LOGGER.debug("Cistern status refresh is waiting for Vineyard Operations: %s", error)

    value = level.get("level_percent")
    if value is None:
        # Create named placeholders immediately so Lovelace never falls back to
        # an anonymous yellow "Entity" card during startup ordering.
        if hass.states.get("sensor.baiamonte_cistern_water_level") is None:
            hass.states.async_set(
                "sensor.baiamonte_cistern_water_level",
                "unavailable",
                {"friendly_name": "Baiamonte Cistern Water Level", "icon": "mdi:storage-tank"},
            )
        if hass.states.get("binary_sensor.baiamonte_cistern_low_water") is None:
            hass.states.async_set(
                "binary_sensor.baiamonte_cistern_low_water",
                "unavailable",
                {"friendly_name": "Baiamonte Cistern Low Water", "device_class": "problem"},
            )
        return

    percent = round(max(0.0, min(100.0, float(value))), 1)
    attributes = _cistern_attributes(level)
    hass.states.async_set(
        "sensor.baiamonte_cistern_water_level",
        percent,
        {
            **attributes,
            "friendly_name": "Baiamonte Cistern Water Level",
            "unit_of_measurement": "%",
            "state_class": "measurement",
            "icon": "mdi:storage-tank",
        },
    )
    hass.states.async_set(
        "binary_sensor.baiamonte_cistern_low_water",
        "on" if percent < 10 else "off",
        {
            **attributes,
            "friendly_name": "Baiamonte Cistern Low Water",
            "device_class": "problem",
            "level_percent": percent,
            "threshold_percent": 10,
        },
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Apply or explicitly restore the pre-authentication page."""
    config_dir = Path(hass.config.config_dir)
    options = config.get(DOMAIN) or {}
    try:
        if options.get("restore", False):
            path = await hass.async_add_executor_job(restore_vendor_page, config_dir)
            _LOGGER.warning("Restored the stock Home Assistant login page at %s", path)
        else:
            result = await hass.async_add_executor_job(apply_branding, config_dir)
            if result.changed:
                _LOGGER.info("Applied the tested Tenuta Baiamonte login page at %s", result.path)
    except BrandingError as error:
        _LOGGER.error("Tenuta Baiamonte login branding was not applied: %s", error)
        return False
    hass.http.register_view(
        BaiamonteMcpProxyView(
            options.get("mcp_proxy_target_url", "http://192.168.0.10:8100/mcp")
        )
    )
    hass.http.register_view(
        BaiamonteLabelProxyView(
            options.get("label_proxy_target_origin", "http://192.168.0.10:8102")
        )
    )
    status_url = str(options.get("vineyard_status_url") or _DEFAULT_STATUS_URL).strip()
    await _async_refresh_cistern_entities(hass, status_url)

    async def _scheduled_cistern_refresh(_now: Any) -> None:
        await _async_refresh_cistern_entities(hass, status_url)

    async_track_time_interval(
        hass,
        _scheduled_cistern_refresh,
        _CISTERN_REFRESH_INTERVAL,
    )
    return True
