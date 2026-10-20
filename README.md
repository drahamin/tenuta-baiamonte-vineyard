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

Each release also updates `release-pair.json`. After CI and review, the normal
developer publication step is one Studio command:

```sh
scripts/publish_release_pair.sh
```

That command requires clean `main` at the exact `origin/main` commit and a
completed successful Release checks run. It builds and signs a fresh archive
from `git archive` of that reviewed commit—not from downloaded release code—
publishes it through the existing website release origin, and waits for the
existing website updater to activate and verify it. Only then does the owner
perform the normal approved Vineyard Operations backup and installation. This is release
preparation performed once per version, not a second owner command after each
installation. GitHub, Home Assistant and the website never receive the private
signing key. Normal post-install verification must confirm that the first
accepted replica snapshot reports the newly installed Vineyard version and the
paired contract.

## System documentation

The maintained operator source is `baiamonte-vineyard/docs/Tenuta_Baiamonte_System_Manual.md`. Build it from the app directory with `python scripts/build_system_manual.py`; this regenerates the branded PDF and every in-app preview page. The builder validates that the manual release matches the current changelog and embeds the complete published history from 1.6.0 through the current release.

Administrators can open **Admin -> Documentation** for the live, secret-free service map, connection readiness, major API routes, access profiles, official records and the generated manual. The app derives the preview page count from the installed files so a manual update does not require a separate hard-coded browser count.
