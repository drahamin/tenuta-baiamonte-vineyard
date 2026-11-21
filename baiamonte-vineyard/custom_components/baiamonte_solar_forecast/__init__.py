"""Expose the Growatt advisory forecast through Home Assistant Energy."""

import logging

import voluptuous as vol

from homeassistant.components.energy.data import async_get_manager
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event

from .energy import FORECAST_SENSOR, hourly_wh

DOMAIN = "baiamonte_solar_forecast"
SOLAR_METER = "sensor.baiamonte_growatt_solar_input_energy"
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Optional("use_for_energy", default=False): cv.boolean,
    }),
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    if DOMAIN in config:
        # The flow sets up the entry, which must wait for this component to finish loading.
        hass.async_create_task(
            hass.config_entries.flow.async_init(DOMAIN, context={"source": "import"}, data=config[DOMAIN]),
            "Import Baiamonte Local Solar Forecast",
        )
    return True


async def async_setup_entry(hass, entry):
    if not entry.data.get("bind_energy"):
        return True

    async def bind_forecast(_event=None):
        if not entry.data.get("bind_energy"):
            return
        state = hass.states.get(FORECAST_SENSOR)
        if state is None or not hourly_wh(state.attributes):
            return
        manager = await async_get_manager(hass)
        if not entry.data.get("bind_energy") or manager.data is None:
            return
        sources = manager.data["energy_sources"]
        matches = [
            source for source in sources
            if source["type"] == "solar" and source.get("stat_energy_from") == SOLAR_METER
        ]
        if len(matches) != 1:
            _LOGGER.warning("Local solar forecast was not selected because the Growatt Energy source was not unique")
            return
        replacement = {**matches[0], "config_entry_solar_forecast": [entry.entry_id]}
        if replacement != matches[0]:
            await manager.async_update({
                "energy_sources": [replacement if source is matches[0] else source for source in sources],
            })
        hass.config_entries.async_update_entry(entry, data={**entry.data, "bind_energy": False})
        _LOGGER.info("Baiamonte local solar forecast selected for the existing Growatt Energy source")

    entry.async_on_unload(async_track_state_change_event(hass, [FORECAST_SENSOR], bind_forecast))
    hass.async_create_task(bind_forecast())
    return True


async def async_unload_entry(_hass, _entry):
    return True
