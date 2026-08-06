from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tenuta Baiamonte"
    db_host: str = "core-mariadb"
    db_port: int = 3306
    db_name: str = "baiamonte_vineyard"
    db_user: str = "baiamonte"
    db_password: str = ""
    api_key: str = ""
    public_feed_token: str = ""
    public_publish_url: str = ""
    public_publish_token: str = ""
    public_publish_minutes: int = 15
    mcp_server_token: str = ""
    mcp_allow_writes: bool = False
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,homeassistant.local:*"
    crew_entry_token: str = ""
    crew_default_name: str = "Giancarlo Pafumi"
    finance_usernames: str = "rahamin,creque,giuseppe"
    operations_usernames: str = "rahamin,creque,giuseppe,giancarlo,sebastian,cognato"
    viewer_usernames: str = "display,tv"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-sol"
    gmail_address: str = ""
    gmail_app_password: str = ""
    gmail_folder: str = "INBOX"
    gmail_allowed_senders: str = "laboratorio@cimalab.it,gabrielefedericistudio@gmail.com"
    gmail_poll_minutes: int = 15
    weather_history_url: str = ""
    weather_sync_minutes: int = 15
    gw2000_entity_prefix: str = "gw2000,ecowitt"
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_allowed_numbers: str = ""
    ha_notifications_enabled: bool = True
    ha_notify_service: str = "persistent_notification/create"
    fattureincloud_token: str = ""
    fattureincloud_company_id: str = ""
    fattureincloud_sync_years: int = 3
    trust_home_assistant_ingress: bool = True
    estate_id: str = "00000000-0000-4000-8000-000000000001"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
