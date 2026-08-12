# Baiamonte Vineyard

This Home Assistant app is the private vineyard and read-only finance interface. It connects to the official MariaDB app over the internal Home Assistant network and appears in the sidebar through Ingress. The existing **Baiamonte Overview** dashboard remains the primary daily dashboard.

## MariaDB setup

Add a separate database and login to the MariaDB app configuration. Keep the existing `homeassistant` entries if the recorder already uses them.

```yaml
databases:
  - homeassistant
  - baiamonte_vineyard
logins:
  - username: homeassistant
    password: YOUR_EXISTING_RECORDER_PASSWORD
  - username: baiamonte
    password: A_NEW_LONG_RANDOM_PASSWORD
rights:
  - username: homeassistant
    database: homeassistant
  - username: baiamonte
    database: baiamonte_vineyard
```

Restart MariaDB after saving. Configure this app with `core-mariadb`, `baiamonte_vineyard`, `baiamonte`, and the new password. The app applies its versioned schema automatically and never uses the Home Assistant recorder database.

## Remote access

With Home Assistant Cloud remote access enabled, open Home Assistant normally and select **Vineyard Operations** in the sidebar. Do not expose MariaDB port 3306.

## Baiamonte Overview

Use the REST sensors and native dashboard cards in the repository's `home-assistant` directory. They show vineyard work, harvest, alerts, hours, and bottles on the existing responsive Baiamonte Overview. Detailed entry and reporting stay inside this app. Finance is deliberately not copied into shared Home Assistant sensor entities; it remains inside the separately authorized Finance tab.

Financial records are private. Only Home Assistant usernames in the app's `finance_usernames` option can open Finance API routes. They are not present in the website feed. The `display` and `tv` kiosk accounts are read-only and never receive Finance.

## Connected information

- **GW2000:** Home Assistant recorder history is backfilled in 14-day sections, then kept current from the live Home Assistant entities. Google Drive's Baiamonte Weather CSV can be imported to fill older history and gaps.
- **Fatture in Cloud:** add a manual read-only token and company ID, then use **Pull latest** on Finance. Fatture in Cloud remains authoritative and this app never writes back.
- **OpenAI:** add the API key to enable automatic report/photo/message extraction and read-only questions. The key stays in the app configuration and is never sent to the browser.
- **Gmail:** use a dedicated Gmail address/app password and restrict `gmail_allowed_senders`. Approved message bodies and attachments are classified into the review inbox automatically.
- **WhatsApp:** the webhook is available at `/webhooks/whatsapp` after a Meta business sender, verification token and app secret are configured. Messages from approved numbers are classified into the same review queue. Alert delivery uses the configured Meta access token and phone-number ID; Meta may require an approved message template outside the customer-service conversation window.
- **Facebook & Instagram:** add a Meta Page access token, Facebook Page ID and Instagram Business Account ID to the protected app configuration. The Social page shows recent posts and permits explicit publishing; it does not publish automatically. Instagram image posts require a public HTTPS image URL.
- **Alerts:** `ha_notify_service` defaults to a Home Assistant persistent notification. It can be changed to an approved mobile-app notify service for push alerts. The Alert Settings page controls event types, minimum severity, Home Assistant delivery, email recipients and WhatsApp recipients; credentials remain in protected add-on options.

### Baiamonte calendar and shared reminders

1. In Home Assistant, open **Settings → Devices & services → Add integration → Google Calendar** and authorize the Google account that owns the shared calendar named **Baiamonte**.
2. After Home Assistant creates the entity, set `planning_calendar_entities` to `calendar.baiamonte` if automatic name discovery does not select it.
3. Google reminders are Google Tasks, not Calendar reminders. Connect a dedicated shared Tasks list through a Home Assistant to-do integration, then set `planning_todo_entities` to that list's exact `todo.*` entity. Do not select the personal `todo.shopping_list` unless it is intentionally being used for vineyard work.

Vineyard Operations remains authoritative for operational tasks and priorities. The TV Work plan page combines those database tasks with read-only upcoming Calendar events and explicitly selected shared to-do items.

## Dashboard management

### GitHub-managed dashboards

Version 0.24.38 installs three maintained YAML dashboards:

- **Vineyard Overview** — complete daily estate and vineyard information.
- **Display Panel** — simplified controls and status for vineyard-building NSPanels. It is hidden from the normal sidebar and opens at `/vineyard-display/home`.
- **Admin** — administrator-only service, update, data health, network, power, solar commissioning, and security diagnostics.

When `manage_ha_dashboards` is enabled, the app copies the release dashboard files into `/config/baiamonte_dashboards`, backs up `configuration.yaml`, merges only the marked dashboard registration block, and runs Home Assistant's configuration check. A failed check restores the backup automatically. Dashboard updates arrive with normal app updates; the registration is one-time and idempotent.

The GitHub repository is the source of truth for the dashboard YAML and REST sensor package. The Overview displays estate-wide status and links into Vineyard Operations. Normal app updates replace only the three managed YAML files; saved credentials and unrelated Home Assistant configuration are not changed.

The release also contains `baiamonte-kiosk-dashboard.yaml` as a compatibility copy of the managed Display Panel. Set each NSPanel's start page to `/vineyard-display/home`. It intentionally contains no Finance, advanced diagnostics, main-breaker switching, or editing cards. Full-screen chrome hiding is configured on the kiosk device or Android Home App, not by granting wider permissions.

The LAN TV webpage separates the saved `tv_camera_entities` list into Entrance cameras (gate, door, driveway and access names) and Vineyard cameras (the remaining selected exterior views). Administrators can now use **Vineyard Operations → TV Config** to manage the full display in one place without opening protected credentials. It controls rotation and refresh timing, browser theme, on-screen controls, camera membership, airport and Etna pages, map brightness, and independent ADS-B, AIS and precipitation-map zoom. Changes are saved back to Home Assistant while every unrelated option and password is preserved.

Set `cellar_mode` to **Demo** while testing the tank layout, or **Live** to show database vessels with their real Home Assistant readings. Demo values can be quietly changed with `cellar_demo_tanks`. Enter one tank per comma using `Name|capacity L|variety|stage|level %|temperature C|density SG|Brix|pH`. The temperature, fill-level, pH and density guardrails are also configurable here. Guardrails create review alerts and never control cellar equipment.

For real tank monitors, set `cellar_live_sensors` to one or more comma-separated mappings in this order: `Tank code or name|level entity|temperature entity|density entity|Brix entity|pH entity`. Example: `T-01|sensor.tank_1_level|sensor.tank_1_temperature|sensor.tank_1_density|sensor.tank_1_brix|sensor.tank_1_ph`. The tank code or name must match its Cellar Operations database record. Level sensors may report percent or liters; Fahrenheit temperature readings are converted to Celsius. Leave any unused sensor position empty but keep its separator, then select **Live**. Set the actual temperature, level, pH and density alert thresholds in **Vineyard Operations → Alert Settings**, not in the add-on configuration.

Cellar Operations includes an AI question card in English or Italian. It sends the current cellar context only when an authorized user presses **Ask AI**. **Send to review inbox** preserves a suggestion as a draft for human review; it does not directly change a tank or cellar record.

The Weather page reads current GW2000 temperature, humidity, rain, wind, gust, pressure, solar radiation, UV and soil moisture through Home Assistant. Its forecast uses the preferred available Home Assistant `weather.*` entity. The large precipitation map reuses the local ADS-B weather-map service so its animated layer and attribution remain intact; if that service or its weather credentials are down, the page reports that state instead of inventing weather.

Set `full_refresh_minutes` from 5–1440 minutes to control the complete system refresh; 60 minutes is the recommended default. Each full cycle updates configured Home Assistant weather history, Gmail intake, Fatture in Cloud, the public harvest website feed, disease/stress screening and operational alerts. Projections and TV/dashboard views recalculate from the refreshed data. Faster subsystem-specific intervals continue to run between complete cycles. Full cycles and any errors appear in the Processing Log.

For the 32-inch entrance TV, open `http://192.168.0.10:8101` in the kiosk browser. This separate LAN page rotates through Today, Vintage, Intelligence, Entrance cameras, the optional Vineyard cameras page, ADS-B, AIS, Work plan, Cellar, and Weather. The Weather page combines a large moving precipitation map with GW2000 readings and the Home Assistant forecast. It refreshes automatically, supports arrow-key/touch navigation and full-screen mode, and exposes no write, Finance, inbox-message, or security-history routes. Keep port 8101 available only on the trusted vineyard LAN/VPN; do not forward it from the internet.

## Operational pages

The selected vintage drives Grapes & Vintage, Projections, Olives, Blocks & Atlas, Issues & Decisions, Treatments, Lab Trends, and Weather Trends. Historical evidence is labeled rather than replaced with zero. Photos or PDFs can be attached in the same quick-entry form for records where visual evidence is useful.

## Website publishing

There are two supported methods:

1. Set `public_publish_url` and `public_publish_token` to push the approved harvest JSON to an HTTPS endpoint on the public website every 15 minutes.
2. For an already-secured reverse proxy, set `public_feed_token` and fetch `/public/v1/harvest.json?token=...`.

Push publishing is preferred because it does not allow inbound access to the vineyard network.
## Mac Codex connection

Vineyard Operations includes an authenticated MCP server for the Codex desktop app. In the Home Assistant app configuration, create a strong `mcp_server_token`, keep `mcp_allow_writes` off for the first test, and expose port `8100`. The local/VPN endpoint is `http://192.168.0.10:8100/mcp`.

In Codex on the Mac, open **Settings → MCP servers → Add server**, choose **Streamable HTTP**, and enter that endpoint. Configure the Home Assistant token as the bearer token and restart Codex. The equivalent shared Codex configuration is:

```toml
[mcp_servers.baiamonte]
url = "http://192.168.0.10:8100/mcp"
bearer_token_env_var = "BAIAMONTE_MCP_TOKEN"
default_tools_approval_mode = "writes"
```

After restart, type `/mcp` and test the read-only `processing_status` tool. Mac monitoring should normally submit messages with `queue_review_item`; it does not silently replace authoritative vineyard records. Enable `mcp_allow_writes` only after the read-only connection is confirmed. Individual database write tools still require explicit confirmation.
