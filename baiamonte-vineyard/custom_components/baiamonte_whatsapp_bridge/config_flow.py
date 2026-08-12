"""Config flow for the Baiamonte WhatsApp Bridge."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import webhook
from homeassistant.components.cloud import (
    CloudNotAvailable,
    CloudNotConnected,
    async_get_or_create_cloudhook,
)
from homeassistant.core import callback

from .const import (
    CONF_CALLBACK_URL,
    CONF_TARGET_URL,
    CONF_WEBHOOK_ID,
    DEFAULT_TARGET_URL,
    DOMAIN,
)


def _valid_target(value: str) -> str:
    """Validate the internal Vineyard Operations webhook URL."""
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise vol.Invalid("Enter a complete HTTP or HTTPS URL")
    if not parsed.path.endswith("/webhooks/whatsapp"):
        raise vol.Invalid("The URL must end in /webhooks/whatsapp")
    return value


class BaiamonteWhatsAppBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the bridge and provision its Nabu Casa cloudhook."""

    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Collect the internal endpoint and create the public callback."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                target_url = _valid_target(user_input[CONF_TARGET_URL])
            except vol.Invalid:
                errors[CONF_TARGET_URL] = "invalid_target_url"
                target_url = None

        if user_input is not None and not errors:
            assert target_url is not None
            webhook_id = webhook.async_generate_id()
            try:
                callback_url = await async_get_or_create_cloudhook(self.hass, webhook_id)
            except (CloudNotAvailable, CloudNotConnected):
                errors["base"] = "cloud_unavailable"
            else:
                self._pending = {
                    CONF_TARGET_URL: target_url,
                    CONF_WEBHOOK_ID: webhook_id,
                    CONF_CALLBACK_URL: callback_url,
                }
                return await self.async_step_confirm()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TARGET_URL,
                    default=(user_input or {}).get(CONF_TARGET_URL, DEFAULT_TARGET_URL),
                ): str
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None):
        """Show the exact Meta callback URL before saving."""
        if not self._pending:
            return await self.async_step_user()
        if user_input is not None:
            return self.async_create_entry(title="Baiamonte WhatsApp", data=self._pending)
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "callback_url": self._pending[CONF_CALLBACK_URL],
                "target_url": self._pending[CONF_TARGET_URL],
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the endpoint options flow."""
        return BaiamonteWhatsAppBridgeOptionsFlow()


class BaiamonteWhatsAppBridgeOptionsFlow(config_entries.OptionsFlow):
    """Allow the internal endpoint to be changed without replacing the cloudhook."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit bridge options."""
        if user_input is not None:
            try:
                target_url = _valid_target(user_input[CONF_TARGET_URL])
            except vol.Invalid:
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_TARGET_URL,
                                default=user_input[CONF_TARGET_URL],
                            ): str
                        }
                    ),
                    errors={CONF_TARGET_URL: "invalid_target_url"},
                )
            return self.async_create_entry(
                title="", data={CONF_TARGET_URL: target_url}
            )
        current = self.config_entry.options.get(
            CONF_TARGET_URL, self.config_entry.data[CONF_TARGET_URL]
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_TARGET_URL, default=current): str}
            ),
        )
