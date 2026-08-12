# Tenuta Baiamonte Home Assistant Apps

This repository publishes the **Baiamonte Vineyard** Home Assistant app.

It contains application code and database migrations only. Vineyard records,
financial workbooks, MariaDB contents, passwords, API keys, Home Assistant
backups, and website tokens are never stored in this repository.

## Living-system control

The private **Operations Control** page is available only to the `rahamin` Home Assistant account. It shows whether each source is updating, the last result, the next expected run, recent processing errors, and the incoming review queue. Each process can be run immediately, enabled or disabled, or given a safe update interval without editing app YAML.

One scheduler owns all recurring app work. Jobs are ordered as **System**, **Sources**, **Intelligence**, and **Publishing**; the complete refresh is a recovery/consistency sweep rather than a second hidden scheduler. The cistern camera, website feed, weather, Gmail, finance, Etna, traffic, disease model, and alerts each have one visible control and audit trail.

Mac and Codex workflows can use the MCP `processing_status` and `queue_review_item` tools, or submit sourced text to `POST /api/v1/intake/mac` using the protected app API key. Submissions are deduplicated and enter **Alerts & Inbox** for AI extraction and human confirmation; they do not silently alter authoritative vineyard records. Gmail and WhatsApp use the same review-first workflow when their protected credentials are configured.

## Install in Home Assistant

Add this repository in **Settings → Apps → App store → Repositories**:

```text
https://github.com/drahamin/tenuta-baiamonte-vineyard
```

Install **Baiamonte Vineyard**, enter the dedicated MariaDB login in the app
configuration, and start the app. After installation, Home Assistant's
**Automatic updates** switch can keep the app on the latest published version.

### Nabu Casa WhatsApp callback

The app also installs the branded **Baiamonte WhatsApp Bridge** custom integration. Restart Home Assistant Core once after the app update, add the integration from **Settings → Devices & services**, and copy the Nabu Casa Callback URL shown by its setup screen into Meta's WhatsApp webhook configuration. The bridge keeps the App Secret and verification token in Vineyard Operations and reports its latest delivery through a Home Assistant status entity.

## Release rule

Every published application change must increment `version` in
`baiamonte-vineyard/config.yaml`. Home Assistant uses that version to offer or
automatically install the update while retaining the saved app configuration.
