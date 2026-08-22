from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


RUNTIME_OPTIONS_PATH = Path("/data/runtime-options.json")


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
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,homeassistant.local:*,192.168.0.10:*"
    crew_entry_token: str = ""
    crew_default_name: str = "Giancarlo Pafumi"
    admin_usernames: str = "rahamin,creque"
    finance_usernames: str = "rahamin,creque,giuseppe"
    operations_usernames: str = "rahamin,creque,giuseppe,giancarlo,sebastian,cognato"
    viewer_usernames: str = "display,tv,ipad"
    worker_usernames: str = "giancarlo:Giancarlo Pafumi,luca:Luca Schiliro Cognato,mattia:Mattia,carmela:Carmela Pafumi,carmella:Carmela Pafumi"
    dedicated_worker_usernames: str = "mattia,carmela,carmella"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-sol"
    gmail_address: str = ""
    gmail_app_password: str = ""
    gmail_folder: str = "INBOX"
    gmail_allowed_senders: str = "laboratorio@cimalab.it,gabrielefedericistudio@gmail.com"
    gmail_poll_minutes: int = 15
    full_refresh_minutes: int = 60
    cistern_camera_entity: str = "camera.192_168_0_54"
    cistern_camera_light_entity: str = ""
    cistern_level_ai_enabled: bool = True
    cistern_level_initial_percent: float = 5.0
    weather_history_url: str = ""
    weather_sync_minutes: int = 15
    prediction_sources_minutes: int = 180
    treatment_planning_water_l: float = 400.0
    treatment_default_sprayer: str = "GS 200 L Mintransporter sprayer · M2192017.1"
    treatment_sprayer_tank_capacity_l: float = 200.0
    treatment_sprayer_usable_capacity_l: float = 0.0
    treatment_sprayer_nozzle_setup: str = "M2030102.1 T-bar with 6 butterfly nozzles; M2400050 hose reel with 50 m 10x17 hose"
    treatment_sprayer_flow_l_min: float = 0.0
    treatment_sprayer_pressure_bar: float = 0.0
    treatment_sprayer_speed_kph: float = 0.0
    treatment_sprayer_carrier_rate_l_ha: float = 0.0
    external_public_location_queries_enabled: bool = False
    sentinel_public_processing_enabled: bool = False
    gw2000_entity_prefix: str = "gw2000,ecowitt"
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_test_access_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_test_phone_number_id: str = "980227578507958"
    whatsapp_test_display_phone_number: str = "+1 555 184 3579"
    whatsapp_business_account_id: str = ""
    whatsapp_test_business_account_id: str = "1194470086141996"
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_allowed_numbers: str = ""
    whatsapp_native_groups_enabled: bool = False
    system_whatsapp_enabled: bool = True
    meta_page_access_token: str = ""
    facebook_page_id: str = ""
    instagram_business_account_id: str = ""
    ha_notifications_enabled: bool = True
    ha_notify_service: str = "persistent_notification/create"
    tv_time_zone: str = "Europe/Rome"
    tv_cycle_seconds: int = 25
    tv_refresh_seconds: int = 120
    tv_camera_entities: str = "camera.gate_doorbell,camera.front_gate,camera.driveway_entrance,camera.vineyard_north,camera.top_vineyard_360,camera.west_etna_view"
    tv_vineyard_camera_page_enabled: bool = True
    tv_adsb_url: str = "http://192.168.0.10:8998"
    tv_ais_url: str = "http://192.168.0.10:8999"
    tv_map_brightness_percent: int = 125
    tv_weather_zoom_level: int = 2
    tv_adsb_zoom_level: int = 0
    tv_ais_zoom_level: int = 0
    tv_adsb_target_size_percent: int = 115
    tv_ais_target_size_percent: int = 100
    tv_theme: str = "auto"
    tv_controls_enabled: bool = True
    tv_home_airport_enabled: bool = True
    tv_home_airport_icao: str = "LICC"
    etna_enabled: bool = True
    etna_refresh_minutes: int = 5
    etna_webcam_codes: str = "Ecv,Emv,Ent,Env"
    cellar_mode: str = "live"
    cellar_demo_tanks: str = "Fermenter 1|1200|Nerello Mascalese|fermentation|82|24.2|1.068|18.5|3.42,Fermenter 2|1200|Nerello Cappuccio|fermentation|76|23.6|1.074|19.8|3.38,Tank 3|750|Grecanico|settling|68|18.4|0.998|5.2|3.25,Tank 4|750|Carricante|aging|61|17.8|0.995|3.6|3.31"
    cellar_live_sensors: str = ""
    cellar_label_public_origin: str = ""
    cellar_label_enrollment_key: str = ""
    cellar_ipad_dashboard_url: str = "http://192.168.0.10:8123/vineyard-ipad/home"
    cellar_temp_min_c: float = 8.0
    cellar_temp_max_c: float = 30.0
    cellar_level_min_pct: float = 5.0
    cellar_level_max_pct: float = 98.0
    cellar_ph_min: float = 2.8
    cellar_ph_max: float = 4.2
    cellar_density_min_sg: float = 0.98
    cellar_density_max_sg: float = 1.2
    planning_calendar_entities: str = ""
    planning_todo_entities: str = ""
    planning_sync_minutes: int = 15
    network_equipment_entities: str = ""
    fattureincloud_token: str = ""
    fattureincloud_company_id: str = ""
    fattureincloud_sync_years: int = 3
    fattureincloud_sync_minutes: int = 360
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_it_client_id: str = ""
    paypal_it_client_secret: str = ""
    paypal_environment: str = "sandbox"
    trust_home_assistant_ingress: bool = True
    estate_id: str = "00000000-0000-4000-8000-000000000001"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def runtime_option(name: str, fallback: Any) -> Any:
    """Read a Home Assistant option without requiring an add-on restart."""
    try:
        values = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
        if name in values and values[name] is not None:
            return values[name]
    except (OSError, ValueError, TypeError):
        pass
    try:
        values = json.loads(Path("/data/options.json").read_text(encoding="utf-8"))
        value = values.get(name, fallback)
        return fallback if value is None else value
    except (OSError, ValueError, TypeError):
        return fallback


@lru_cache
def addon_version() -> str:
    """Read the packaged add-on version for automatic static-asset cache keys."""
    try:
        match = re.search(r'^version:\s*["\']?([^"\'\s]+)', (Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"), re.MULTILINE)
        return match.group(1) if match else "development"
    except OSError:
        return "development"
