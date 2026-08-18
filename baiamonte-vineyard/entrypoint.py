import json
import os
import signal
import secrets
import subprocess
import sys
import time
import urllib.request

# entrypoint.py is installed at / while the application modules live in the
# image work directory. Add that directory explicitly before importing them.
sys.path.insert(0, "/opt/baiamonte")
from scripts.dashboard_manager import deploy_dashboards
from scripts.integration_manager import deploy_integrations


with open("/data/options.json", "r", encoding="utf-8") as handle:
    options = json.load(handle)


def ensure_new_defaults(values: dict) -> dict:
    """Backfill new options without replacing any saved credentials or choices."""
    defaults = {
        "tv_map_brightness_percent": 125,
        "tv_weather_zoom_level": 2,
        "tv_adsb_zoom_level": 0,
        "tv_ais_zoom_level": 0,
        "tv_adsb_target_size_percent": 115,
        "tv_ais_target_size_percent": 100,
        "tv_theme": "auto",
        "tv_controls_enabled": True,
        "tv_home_airport_enabled": True,
        "tv_home_airport_icao": "LICC",
        "full_refresh_minutes": 60,
        "mcp_allowed_hosts": "localhost:*,127.0.0.1:*,homeassistant.local:*,192.168.0.10:*",
        "cistern_camera_entity": "camera.192_168_0_54",
        "cistern_camera_light_entity": "",
        "cistern_level_ai_enabled": True,
        "cistern_level_initial_percent": 5.0,
        "etna_enabled": True,
        "etna_refresh_minutes": 5,
        "etna_webcam_codes": "Ecv,Emv,Ent,Env",
        "cellar_mode": "demo",
        "cellar_demo_tanks": "Fermenter 1|1200|Nerello Mascalese|fermentation|82|24.2|1.068|18.5|3.42,Fermenter 2|1200|Nerello Cappuccio|fermentation|76|23.6|1.074|19.8|3.38,Tank 3|750|Grecanico|settling|68|18.4|0.998|5.2|3.25,Tank 4|750|Carricante|aging|61|17.8|0.995|3.6|3.31",
        "cellar_temp_min_c": 8.0,
        "cellar_temp_max_c": 30.0,
        "cellar_level_min_pct": 5.0,
        "cellar_level_max_pct": 98.0,
        "cellar_ph_min": 2.8,
        "cellar_ph_max": 4.2,
        "cellar_density_min_sg": 0.98,
        "cellar_density_max_sg": 1.2,
        "manage_ha_dashboards": True,
        "system_whatsapp_enabled": True,
    }
    missing = {key: value for key, value in defaults.items() if key not in values}
    allowed_hosts = str(values.get("mcp_allowed_hosts") or defaults["mcp_allowed_hosts"])
    amendments = {}
    if "192.168.0.10:" not in allowed_hosts:
        amendments["mcp_allowed_hosts"] = allowed_hosts.rstrip(",") + ",192.168.0.10:*"
    if not missing and not amendments:
        return values
    merged = {**values, **missing, **amendments}
    token = os.environ.get("SUPERVISOR_TOKEN")
    if token:
        request = urllib.request.Request(
            "http://supervisor/addons/self/options",
            data=json.dumps({"options": merged}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15):
                pass
        except Exception:
            pass
    return merged


options = ensure_new_defaults(options)

deploy_integrations()

if options.get("manage_ha_dashboards", True):
    deploy_dashboards()

mapping = {
    "db_host": "DB_HOST",
    "db_port": "DB_PORT",
    "db_name": "DB_NAME",
    "db_user": "DB_USER",
    "db_password": "DB_PASSWORD",
    "api_key": "API_KEY",
    "public_feed_token": "PUBLIC_FEED_TOKEN",
    "public_publish_url": "PUBLIC_PUBLISH_URL",
    "public_publish_token": "PUBLIC_PUBLISH_TOKEN",
    "public_publish_minutes": "PUBLIC_PUBLISH_MINUTES",
    "mcp_server_token": "MCP_SERVER_TOKEN",
    "mcp_allow_writes": "MCP_ALLOW_WRITES",
    "mcp_allowed_hosts": "MCP_ALLOWED_HOSTS",
    "crew_entry_token": "CREW_ENTRY_TOKEN",
    "crew_default_name": "CREW_DEFAULT_NAME",
    "admin_usernames": "ADMIN_USERNAMES",
    "finance_usernames": "FINANCE_USERNAMES",
    "operations_usernames": "OPERATIONS_USERNAMES",
    "viewer_usernames": "VIEWER_USERNAMES",
    "worker_usernames": "WORKER_USERNAMES",
    "dedicated_worker_usernames": "DEDICATED_WORKER_USERNAMES",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "gmail_address": "GMAIL_ADDRESS",
    "gmail_app_password": "GMAIL_APP_PASSWORD",
    "gmail_folder": "GMAIL_FOLDER",
    "gmail_allowed_senders": "GMAIL_ALLOWED_SENDERS",
    "gmail_poll_minutes": "GMAIL_POLL_MINUTES",
    "full_refresh_minutes": "FULL_REFRESH_MINUTES",
    "cistern_camera_entity": "CISTERN_CAMERA_ENTITY",
    "cistern_camera_light_entity": "CISTERN_CAMERA_LIGHT_ENTITY",
    "cistern_level_ai_enabled": "CISTERN_LEVEL_AI_ENABLED",
    "cistern_level_initial_percent": "CISTERN_LEVEL_INITIAL_PERCENT",
    "weather_history_url": "WEATHER_HISTORY_URL",
    "weather_sync_minutes": "WEATHER_SYNC_MINUTES",
    "gw2000_entity_prefix": "GW2000_ENTITY_PREFIX",
    "whatsapp_verify_token": "WHATSAPP_VERIFY_TOKEN",
    "whatsapp_access_token": "WHATSAPP_ACCESS_TOKEN",
    "whatsapp_test_access_token": "WHATSAPP_TEST_ACCESS_TOKEN",
    "whatsapp_app_secret": "WHATSAPP_APP_SECRET",
    "whatsapp_phone_number_id": "WHATSAPP_PHONE_NUMBER_ID",
    "whatsapp_test_phone_number_id": "WHATSAPP_TEST_PHONE_NUMBER_ID",
    "whatsapp_test_display_phone_number": "WHATSAPP_TEST_DISPLAY_PHONE_NUMBER",
    "whatsapp_business_account_id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
    "whatsapp_test_business_account_id": "WHATSAPP_TEST_BUSINESS_ACCOUNT_ID",
    "whatsapp_graph_api_version": "WHATSAPP_GRAPH_API_VERSION",
    "whatsapp_allowed_numbers": "WHATSAPP_ALLOWED_NUMBERS",
    "whatsapp_native_groups_enabled": "WHATSAPP_NATIVE_GROUPS_ENABLED",
    "system_whatsapp_enabled": "SYSTEM_WHATSAPP_ENABLED",
    "meta_page_access_token": "META_PAGE_ACCESS_TOKEN",
    "facebook_page_id": "FACEBOOK_PAGE_ID",
    "instagram_business_account_id": "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "ha_notifications_enabled": "HA_NOTIFICATIONS_ENABLED",
    "ha_notify_service": "HA_NOTIFY_SERVICE",
    "tv_time_zone": "TV_TIME_ZONE",
    "tv_cycle_seconds": "TV_CYCLE_SECONDS",
    "tv_refresh_seconds": "TV_REFRESH_SECONDS",
    "tv_camera_entities": "TV_CAMERA_ENTITIES",
    "tv_vineyard_camera_page_enabled": "TV_VINEYARD_CAMERA_PAGE_ENABLED",
    "tv_adsb_url": "TV_ADSB_URL",
    "tv_ais_url": "TV_AIS_URL",
    "tv_map_brightness_percent": "TV_MAP_BRIGHTNESS_PERCENT",
    "tv_weather_zoom_level": "TV_WEATHER_ZOOM_LEVEL",
    "tv_adsb_zoom_level": "TV_ADSB_ZOOM_LEVEL",
    "tv_ais_zoom_level": "TV_AIS_ZOOM_LEVEL",
    "tv_adsb_target_size_percent": "TV_ADSB_TARGET_SIZE_PERCENT",
    "tv_ais_target_size_percent": "TV_AIS_TARGET_SIZE_PERCENT",
    "tv_theme": "TV_THEME",
    "tv_controls_enabled": "TV_CONTROLS_ENABLED",
    "tv_home_airport_enabled": "TV_HOME_AIRPORT_ENABLED",
    "tv_home_airport_icao": "TV_HOME_AIRPORT_ICAO",
    "etna_enabled": "ETNA_ENABLED",
    "etna_refresh_minutes": "ETNA_REFRESH_MINUTES",
    "etna_webcam_codes": "ETNA_WEBCAM_CODES",
    "cellar_mode": "CELLAR_MODE",
    "cellar_demo_tanks": "CELLAR_DEMO_TANKS",
    "cellar_live_sensors": "CELLAR_LIVE_SENSORS",
    "cellar_label_public_origin": "CELLAR_LABEL_PUBLIC_ORIGIN",
    "cellar_label_enrollment_key": "CELLAR_LABEL_ENROLLMENT_KEY",
    "cellar_ipad_dashboard_url": "CELLAR_IPAD_DASHBOARD_URL",
    "cellar_temp_min_c": "CELLAR_TEMP_MIN_C",
    "cellar_temp_max_c": "CELLAR_TEMP_MAX_C",
    "cellar_level_min_pct": "CELLAR_LEVEL_MIN_PCT",
    "cellar_level_max_pct": "CELLAR_LEVEL_MAX_PCT",
    "cellar_ph_min": "CELLAR_PH_MIN",
    "cellar_ph_max": "CELLAR_PH_MAX",
    "cellar_density_min_sg": "CELLAR_DENSITY_MIN_SG",
    "cellar_density_max_sg": "CELLAR_DENSITY_MAX_SG",
    "planning_calendar_entities": "PLANNING_CALENDAR_ENTITIES",
    "planning_todo_entities": "PLANNING_TODO_ENTITIES",
    "planning_sync_minutes": "PLANNING_SYNC_MINUTES",
    "network_equipment_entities": "NETWORK_EQUIPMENT_ENTITIES",
    "fattureincloud_token": "FATTUREINCLOUD_TOKEN",
    "fattureincloud_company_id": "FATTUREINCLOUD_COMPANY_ID",
    "fattureincloud_sync_years": "FATTUREINCLOUD_SYNC_YEARS",
    "fattureincloud_sync_minutes": "FATTUREINCLOUD_SYNC_MINUTES",
    "manage_ha_dashboards": "MANAGE_HA_DASHBOARDS",
}
for option, environment in mapping.items():
    if option in options and options[option] is not None:
        os.environ[environment] = str(options[option])
os.environ["TRUST_HOME_ASSISTANT_INGRESS"] = "true"

commands = [
    ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--proxy-headers"],
    ["uvicorn", "app.display_server:display_app", "--host", "0.0.0.0", "--port", "8101", "--proxy-headers"],
    ["uvicorn", "app.tank_label_server:display_app", "--host", "0.0.0.0", "--port", "8102", "--proxy-headers"],
]
if options.get("system_whatsapp_enabled", True):
    bridge_token_path = "/data/system-whatsapp-bridge-token"
    try:
        with open(bridge_token_path, "r", encoding="utf-8") as handle:
            bridge_token = handle.read().strip()
    except OSError:
        bridge_token = ""
    if not bridge_token:
        bridge_token = secrets.token_urlsafe(36)
        with open(bridge_token_path, "w", encoding="utf-8") as handle:
            handle.write(bridge_token)
        os.chmod(bridge_token_path, 0o600)
    os.environ["SYSTEM_WHATSAPP_BRIDGE_TOKEN"] = bridge_token
    commands.append(["node", "/opt/baiamonte/system_whatsapp/server.mjs"])
if os.environ.get("MCP_SERVER_TOKEN"):
    commands.append(["uvicorn", "app.mcp_server:http_app", "--host", "0.0.0.0", "--port", "8100", "--proxy-headers"])

processes = [subprocess.Popen(command) for command in commands]


def stop_all(signum: int, _frame: object) -> None:
    for process in processes:
        if process.poll() is None:
            process.send_signal(signum)


signal.signal(signal.SIGTERM, stop_all)
signal.signal(signal.SIGINT, stop_all)

while True:
    for process in processes:
        code = process.poll()
        if code is not None:
            stop_all(signal.SIGTERM, None)
            for peer in processes:
                if peer is not process:
                    try:
                        peer.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        peer.kill()
            sys.exit(code)
    time.sleep(0.5)
