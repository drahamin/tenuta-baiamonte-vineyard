# Baiamonte Vineyard

This Home Assistant app is the private vineyard, finance, and funding interface. It connects to the official MariaDB app over the internal Home Assistant network and appears in the sidebar through Ingress. The existing **Baiamonte Overview** dashboard remains the primary daily dashboard.

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
- **WhatsApp:** the webhook is available at `/webhooks/whatsapp` after a Meta business sender, verification token and app secret are configured. Messages from approved numbers are classified into the same review queue.
- **Alerts:** `ha_notify_service` defaults to a Home Assistant persistent notification. It can be changed to an approved mobile-app notify service for push alerts.

## Dashboard management

The GitHub repository's `dashboard` directory is the source of truth for the Baiamonte Overview YAML and REST sensor package. The Overview displays only estate-wide vineyard summaries and links into Vineyard Operations. App auto-updates do not silently overwrite the live dashboard; apply the tested dashboard file as a separate controlled update.

The release also contains `baiamonte-kiosk-dashboard.yaml`. Add it as a separate YAML dashboard, then set the `display` profile's default view to `/baiamonte-kiosk/nspanel` and the `tv` profile's default view to `/baiamonte-kiosk/tv`. It intentionally contains no Finance, camera, security-history, or editing cards. Full-screen chrome hiding is configured on the kiosk device or Android Home App, not by granting wider permissions.

## Operational pages

The selected vintage drives Grapes & Vintage, Projections, Olives, Blocks & Atlas, Issues & Decisions, Treatments, Lab Trends, and Weather Trends. Historical evidence is labeled rather than replaced with zero. Photos or PDFs can be attached in the same quick-entry form for records where visual evidence is useful.

## Website publishing

There are two supported methods:

1. Set `public_publish_url` and `public_publish_token` to push the approved harvest JSON to an HTTPS endpoint on the public website every 15 minutes.
2. For an already-secured reverse proxy, set `public_feed_token` and fetch `/public/v1/harvest.json?token=...`.

Push publishing is preferred because it does not allow inbound access to the vineyard network.
