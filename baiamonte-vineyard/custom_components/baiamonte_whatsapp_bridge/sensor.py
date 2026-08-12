"""Status sensor for the Baiamonte WhatsApp Bridge."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [BaiamonteWhatsAppBridgeSensor(hass.data[DOMAIN][entry.entry_id], entry)]
    )


class BaiamonteWhatsAppBridgeSensor(SensorEntity):
    """Show whether Meta events are reaching Vineyard Operations."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:whatsapp"
    _attr_name = "Status"

    def __init__(self, runtime, entry: ConfigEntry) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Baiamonte WhatsApp Bridge",
            manufacturer="Tenuta Baiamonte",
            model="Nabu Casa Cloudhook Bridge",
        )

    @property
    def native_value(self):
        return self.runtime.state

    @property
    def extra_state_attributes(self):
        return {
            "callback_url": self.runtime.callback_url,
            "target_url": self.runtime.target_url,
            "last_delivery": self.runtime.last_delivery,
            "last_method": self.runtime.last_method,
            "last_http_status": self.runtime.last_http_status,
            "last_error": self.runtime.last_error,
        }

    async def async_added_to_hass(self) -> None:
        self.runtime.listeners.append(self._refresh)

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh in self.runtime.listeners:
            self.runtime.listeners.remove(self._refresh)

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()
