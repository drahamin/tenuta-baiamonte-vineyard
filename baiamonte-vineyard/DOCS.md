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

With Home Assistant Cloud remote access enabled, open Home Assistant normally and select **Vineyard** in the sidebar. Do not expose MariaDB port 3306.

## Baiamonte Overview

Use the REST sensors and native dashboard cards in the repository's `home-assistant` directory. They show vineyard work, harvest, alerts, hours, and bottles on the existing responsive Baiamonte Overview. Detailed entry and reporting stay inside this app. Finance is deliberately not copied into shared Home Assistant sensor entities; it remains inside the separately authorized Finance tab.

Financial records are private. Only Home Assistant usernames in the app's `finance_usernames` option can open Finance API routes. They are not present in the website feed. The `display` and `tv` kiosk accounts are read-only and never receive Finance.

## Website publishing

There are two supported methods:

1. Set `public_publish_url` and `public_publish_token` to push the approved harvest JSON to an HTTPS endpoint on the public website every 15 minutes.
2. For an already-secured reverse proxy, set `public_feed_token` and fetch `/public/v1/harvest.json?token=...`.

Push publishing is preferred because it does not allow inbound access to the vineyard network.
