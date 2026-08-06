# Tenuta Baiamonte Home Assistant Apps

This repository publishes the **Baiamonte Vineyard** Home Assistant app.

It contains application code and database migrations only. Vineyard records,
financial workbooks, MariaDB contents, passwords, API keys, Home Assistant
backups, and website tokens are never stored in this repository.

## Install in Home Assistant

Add this repository in **Settings → Apps → App store → Repositories**:

```text
https://github.com/drahamin/tenuta-baiamonte-vineyard
```

Install **Baiamonte Vineyard**, enter the dedicated MariaDB login in the app
configuration, and start the app. After installation, Home Assistant's
**Automatic updates** switch can keep the app on the latest published version.

## Release rule

Every published application change must increment `version` in
`baiamonte-vineyard/config.yaml`. Home Assistant uses that version to offer or
automatically install the update while retaining the saved app configuration.

