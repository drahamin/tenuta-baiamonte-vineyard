"""Config flow for the native Energy forecast source."""

from homeassistant import config_entries

from . import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._create_forecast_entry(use_for_energy=False)

    async def async_step_import(self, user_input):
        return await self._create_forecast_entry(use_for_energy=bool(user_input.get("use_for_energy")))

    async def _create_forecast_entry(self, *, use_for_energy):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Baiamonte Local Solar Forecast",
            data={"bind_energy": use_for_energy},
        )
