"""Baiamonte Nabu Casa bridge for the Vineyard Operations WhatsApp webhook."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any, Callable

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components import webhook
from homeassistant.components.cloud import CloudNotAvailable, async_delete_cloudhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CALLBACK_URL, CONF_TARGET_URL, CONF_WEBHOOK_ID, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)
_FORWARDED_HEADERS = {
    "content-type",
    "user-agent",
    "x-hub-signature",
    "x-hub-signature-256",
}


@dataclass
class BridgeRuntime:
    """Runtime status shared with the diagnostic sensor."""

    callback_url: str
    target_url: str
    state: str = "ready"
    last_delivery: datetime | None = None
    last_method: str | None = None
    last_http_status: int | None = None
    last_error: str | None = None
    listeners: list[Callable[[], None]] = field(default_factory=list)

    @callback
    def notify(self) -> None:
        for listener in self.listeners:
            listener()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the public cloud webhook and its local relay."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    target_url = entry.options.get(CONF_TARGET_URL, entry.data[CONF_TARGET_URL])
    runtime = BridgeRuntime(entry.data[CONF_CALLBACK_URL], target_url)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    async def handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: Any
    ) -> web.Response:
        """Relay Meta verification and signed notifications without altering them."""
        # Nabu Casa delivers a Home Assistant MockRequest, while a direct local
        # call delivers aiohttp.web.Request. Both expose the same content reader.
        body = await request.content.read()
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _FORWARDED_HEADERS
        }
        session = async_get_clientsession(hass)
        try:
            async with session.request(
                request.method,
                runtime.target_url,
                params=list(request.query.items()),
                data=body,
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=30),
            ) as response:
                response_body = await response.read()
                runtime.last_delivery = datetime.now().astimezone()
                runtime.last_method = request.method
                runtime.last_http_status = response.status
                runtime.last_error = (
                    None
                    if response.status < 400
                    else response_body.decode("utf-8", "replace")[:500]
                )
                runtime.state = "receiving" if response.status < 400 else "error"
                runtime.notify()
                return web.Response(
                    body=response_body,
                    status=response.status,
                    content_type=response.content_type,
                    charset=response.charset,
                )
        except (ClientError, TimeoutError) as error:
            runtime.last_delivery = datetime.now().astimezone()
            runtime.last_method = request.method
            runtime.last_http_status = 502
            runtime.last_error = str(error)[:500]
            runtime.state = "error"
            runtime.notify()
            _LOGGER.warning("Baiamonte WhatsApp relay failed: %s", error)
            return web.Response(text="Vineyard Operations is temporarily unavailable", status=502)

    webhook.async_register(
        hass,
        DOMAIN,
        "Baiamonte WhatsApp",
        webhook_id,
        handle_webhook,
        local_only=False,
        allowed_methods={"GET", "HEAD", "POST"},
    )

    async def stop_listener(_: Event) -> None:
        webhook.async_unregister(hass, webhook_id)

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_listener))
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the bridge cleanly."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the Nabu Casa cloudhook when the integration is deleted."""
    try:
        await async_delete_cloudhook(hass, entry.data[CONF_WEBHOOK_ID])
    except CloudNotAvailable:
        _LOGGER.warning(
            "Could not remove the Baiamonte cloudhook because Home Assistant Cloud is unavailable"
        )


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
