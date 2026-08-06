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
    trust_home_assistant_ingress: bool = True
    estate_id: str = "00000000-0000-4000-8000-000000000001"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
