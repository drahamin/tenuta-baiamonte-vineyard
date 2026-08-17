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

## Solar forecast

Install and configure the Solcast PV Forecast integration in Home Assistant. Vineyard Operations discovers the Solcast sensors even when Home Assistant gives them a customized prefix. Today, the TV display and the managed dashboards show the Solcast cloudier P10, most-likely P50 and sunnier P90 cases when the integration supplies those attributes. Missing probability values remain visibly unavailable; the app does not manufacture a range. Live production remains a separate Growatt measurement.

## Remote access

With Home Assistant Cloud remote access enabled, open Home Assistant normally and select **Vineyard Operations** in the sidebar. Do not expose MariaDB port 3306.

## Baiamonte Overview

Use the REST sensors and native dashboard cards in the repository's `home-assistant` directory. They show vineyard work, harvest, alerts, hours, and bottles on the existing responsive Baiamonte Overview. Detailed entry and reporting stay inside this app. Finance is deliberately not copied into shared Home Assistant sensor entities; it remains inside the separately authorized Finance tab.

Financial records are private. Only Home Assistant usernames in the app's `finance_usernames` option can open Finance API routes. They are not present in the website feed. The `display` and `tv` kiosk accounts are read-only and never receive Finance.

## Connected information

- **GW2000:** Home Assistant recorder history is backfilled in 14-day sections, then kept current from the live Home Assistant entities. Google Drive's Baiamonte Weather CSV can be imported to fill older history and gaps.
- **Fatture in Cloud:** add a manual read-only token and company ID, then use **Pull latest** on Finance. Fatture in Cloud remains authoritative and this app never writes back.
- **OpenAI:** add the API key to enable automatic report/photo/message extraction and read-only questions. The key stays in the app configuration and is never sent to the browser.
- **Gmail:** use a dedicated Gmail address/app password. The Communications page can open the real mailbox, send and download photos/documents, mark read/unread, star, archive and move mail to Trash. Recent inbound mail is ingested even if it was already opened; message text and every attachment are classified into the review inbox automatically. `gmail_allowed_senders` identifies trusted senders, while mail from another sender is retained with an explicit verification warning. Delete is intentionally recoverable; the app does not permanently expunge mail.
- **WhatsApp:** the protected processor remains at `/webhooks/whatsapp` after a Meta business sender, verification token and app secret are configured. The app now installs the branded **Baiamonte WhatsApp Bridge** custom integration. After one Home Assistant Core restart, add it from **Settings → Devices & services → Add integration**. It provisions a Nabu Casa cloudhook, displays the exact Meta Callback URL, and relays the untouched GET challenge and signed POST body to Vineyard Operations. Use the same verification token in Meta and the app configuration. Add the Business Account ID to load approved templates. The page verifies the sender live and displays Meta's actual error instead of assuming a filled token is connected. Named delivery lists send separate one-to-one messages. If Meta confirms that the account is eligible for the restricted Groups API, enable `whatsapp_native_groups_enabled` and save the Meta-created group ID; this does not make the business sender a participant in an arbitrary existing personal group. Messages from approved numbers enter the same review queue.
- **iMessage:** create a separate Baiamonte Apple Account and sign it into Messages under a dedicated macOS user. A local Mac relay connects that account to the app using `imessage_bridge_url` and `imessage_bridge_token`; Apple credentials never enter Home Assistant. Set `imessage_allowed_handles` to the vineyard workers' comma-separated phone numbers/Apple addresses for an additional inbound and outbound guardrail. The relay sends inbound events to `/webhooks/imessage` using the same bearer token.
- **Facebook & Instagram:** add a Meta Page access token, Facebook Page ID and Instagram Business Account ID to the protected app configuration. The Social page shows recent posts and permits explicit publishing; it does not publish automatically. Instagram image posts require a public HTTPS image URL.
- **Alerts:** `ha_notify_service` defaults to a Home Assistant persistent notification. It can be changed to an approved mobile-app notify service for push alerts. The Alert Settings page controls event types, minimum severity, Home Assistant delivery, email recipients and WhatsApp recipients; credentials remain in protected add-on options.

### Baiamonte calendar and shared reminders

1. In Home Assistant, open **Settings → Devices & services → Add integration → Google Calendar** and authorize the Google account that owns the shared calendar named **Baiamonte**.
2. After Home Assistant creates the entity, set `planning_calendar_entities` to `calendar.baiamonte` if automatic name discovery does not select it.
3. Google reminders are Google Tasks, not Calendar reminders. Connect a dedicated shared Tasks list through a Home Assistant to-do integration, then set `planning_todo_entities` to that list's exact `todo.*` entity. Do not select the personal `todo.shopping_list` unless it is intentionally being used for vineyard work.

Vineyard Operations remains authoritative for operational tasks and priorities. The TV Work plan page combines those database tasks with read-only upcoming Calendar events and explicitly selected shared to-do items.

## Dashboard management

### GitHub-managed dashboards

The app installs four maintained YAML dashboards:

- **Vineyard Overview** — complete daily estate and vineyard information.
- **Display Panel** — simplified controls and status for vineyard-building NSPanels. It is hidden from the normal sidebar and opens at `/vineyard-display/home`.
- **Baiamonte iPad** — a larger, finance-free touch dashboard for the `ipad` account with weather, live and forecast solar, power and lighting controls, cameras, security, vineyard operations, media and AI links. It is hidden from the normal sidebar and opens at `/vineyard-ipad/home`.
- **Admin** — administrator-only service, update, data health, network, power, solar commissioning, and security diagnostics.

When `manage_ha_dashboards` is enabled, the app copies the release dashboard files into `/config/baiamonte_dashboards`, backs up `configuration.yaml`, merges only the marked dashboard registration block, and runs Home Assistant's configuration check. A failed check restores the backup automatically. Dashboard updates arrive with normal app updates; the registration is one-time and idempotent.

The GitHub repository is the source of truth for the dashboard YAML and REST sensor package. The Overview displays estate-wide status and links into Vineyard Operations. Normal app updates replace only the four managed YAML files; saved credentials and unrelated Home Assistant configuration are not changed.

The release also contains `baiamonte-kiosk-dashboard.yaml` as a compatibility copy of the managed Display Panel. Set each NSPanel's start page to `/vineyard-display/home`. For the dedicated iPad, sign in as `ipad`, open `/vineyard-ipad/home`, and select **Baiamonte iPad** under **Profile → Default dashboard** once on that device. Both dashboards exclude Finance. Full-screen chrome hiding is configured on the kiosk device or Home Assistant app, not by granting wider permissions.

The installer resolves the Home Assistant IDs for the `display` and `ipad` logins and applies view visibility to their matching managed dashboards. Home Assistant still stores the actual default-dashboard choice in each signed-in device profile, so make the one-time selection on every NSPanel and on the iPad. Human standard users start on **Vineyard Overview**; David and Wendy are administrators, while all other vineyard people remain standard users. The `mqtt` login is retained as a non-person service credential and should not have a Person profile, location tracker or dashboard destination.

The administrator dashboard includes **User Tracking**, a live Home Assistant map and compact detail view for the named vineyard people. It shows the latest reported zone or coordinates, tracker source, GPS accuracy, last update and seven-day presence history. Location reporting depends on each person's Home Assistant companion-app permission and chosen device tracker; an unavailable phone cannot be interpreted as a current physical location.

The LAN TV webpage separates the saved `tv_camera_entities` list into Entrance cameras (gate, door, driveway and access names) and Vineyard cameras (the remaining selected exterior views). Administrators can now use **Vineyard Operations → TV Config** to manage the full display in one place without opening protected credentials. It controls rotation and refresh timing, browser theme, on-screen controls, camera membership, airport and Etna pages, map brightness, independent ADS-B/AIS/precipitation zoom, and separate aircraft/vessel target sizes. Changes are saved back to Home Assistant while every unrelated option and password is preserved.

Set `cellar_mode` to **Demo** while testing the tank layout, or **Live** to show database vessels with their real Home Assistant readings. Demo values can be quietly changed with `cellar_demo_tanks`. Enter one tank per comma using `Name|capacity L|variety|stage|level %|temperature C|density SG|Brix|pH`. The temperature, fill-level, pH and density guardrails are also configurable here. Guardrails create review alerts and never control cellar equipment.

For real tank monitors, set `cellar_live_sensors` to one or more comma-separated mappings in this order: `Tank code or name|level entity|temperature entity|density entity|Brix entity|pH entity`. Example: `T-01|sensor.tank_1_level|sensor.tank_1_temperature|sensor.tank_1_density|sensor.tank_1_brix|sensor.tank_1_ph`. The tank code or name must match its Cellar Operations database record. Level sensors may report percent or liters; Fahrenheit temperature readings are converted to Celsius. Leave any unused sensor position empty but keep its separator, then select **Live**. Set the actual temperature, level, pH and density alert thresholds in **Vineyard Operations → Alert Settings**, not in the add-on configuration.

Cellar Operations includes an AI question card in English or Italian. It sends the current cellar context only when an authorized user presses **Ask AI**. **Send to review inbox** preserves a suggestion as a draft for human review; it does not directly change a tank or cellar record.

### Cellar legal labels and tablets

Vineyard Operations serves the cellar identification display on trusted LAN/VPN port `8102`. In **Operations → Agronomy & Cellar → Tank register → Cellar legal labels & tablets**, the enologist can maintain the wine type, vintage, Italian origin, denomination, contents, processing phase, racking history and legal notes for the wine lot currently assigned to a tank. The saved legal identity belongs to the wine lot, so it follows that wine through later tank transfers instead of becoming an editable property of the physical vessel.

Every physical tank receives its own permanent `/tank/<token>` label URL. Dedicated Android tablets should normally use the permanent `/kiosk/<token>` URL created in the same panel. An administrator can reassign that tablet to another tank without touching the tablet browser or changing its bookmark. Tablets can be added, left unassigned, reassigned or retired; removal does not delete cellar, wine or audit history.

The display refreshes every 30 seconds and shows the Baiamonte logo, restrained process motion, animated fill level, capacity, volume, temperature, density, Brix, pH and last reading time. Manual-mode tanks read the authoritative database values. Sensor-mode tanks overlay only explicitly configured Home Assistant sensor mappings and retain the last recorded value with a visible fault state if the sensor request fails. Retired tanks stop serving a live label while their final legal and transfer records remain in the read-only archive.

The label editor is a cellar record-keeping aid, not an automatic legal-compliance determination. The responsible enologist must confirm the required wording and classification for each wine.

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
