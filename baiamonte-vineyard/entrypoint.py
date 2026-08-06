import json
import os
import signal
import subprocess
import sys
import time


with open("/data/options.json", "r", encoding="utf-8") as handle:
    options = json.load(handle)

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
    "finance_usernames": "FINANCE_USERNAMES",
    "operations_usernames": "OPERATIONS_USERNAMES",
    "viewer_usernames": "VIEWER_USERNAMES",
}
for option, environment in mapping.items():
    if option in options and options[option] is not None:
        os.environ[environment] = str(options[option])
os.environ["TRUST_HOME_ASSISTANT_INGRESS"] = "true"

commands = [
    ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--proxy-headers"],
]
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
