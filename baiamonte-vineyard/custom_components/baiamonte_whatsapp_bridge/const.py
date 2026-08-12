"""Constants for the Baiamonte WhatsApp Bridge."""

from homeassistant.const import Platform

DOMAIN = "baiamonte_whatsapp_bridge"
CONF_TARGET_URL = "target_url"
CONF_WEBHOOK_ID = "webhook_id"
CONF_CALLBACK_URL = "callback_url"

DEFAULT_TARGET_URL = "http://192.168.0.10:8099/webhooks/whatsapp"
PLATFORMS = [Platform.SENSOR]
