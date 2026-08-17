"""Apply the Mobile Safari-tested Tenuta Baiamonte login treatment."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .brander import BrandingError, apply_branding, restore_vendor_page
from .mcp_proxy import BaiamonteMcpProxyView

DOMAIN = "baiamonte_branding"
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Apply or explicitly restore the pre-authentication page."""
    config_dir = Path(hass.config.config_dir)
    options = config.get(DOMAIN) or {}
    try:
        if options.get("restore", False):
            path = await hass.async_add_executor_job(restore_vendor_page, config_dir)
            _LOGGER.warning("Restored the stock Home Assistant login page at %s", path)
            return True
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
    return True
