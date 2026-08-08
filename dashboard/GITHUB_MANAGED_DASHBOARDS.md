# GitHub-managed Home Assistant dashboards

The repository is the authoritative source for three Home Assistant dashboards:

- `baiamonte-vineyard/dashboards/vineyard-overview.yaml` — the full estate and vineyard overview.
- `baiamonte-vineyard/dashboards/display-panel.yaml` — a simplified, touch-friendly NSPanel interface.
- `baiamonte-vineyard/dashboards/admin.yaml` — admin-only service, network, power, update, and diagnostic views.

Home Assistant registers them once under `lovelace: dashboards:`. The intended URLs are:

- `/vineyard-overview`
- `/vineyard-display/home`
- `/vineyard-admin/system`

## Safe migration

1. Back up `/config/configuration.yaml` and the three existing UI-controlled dashboards.
2. Copy the dashboard files to `/config/baiamonte_dashboards/`.
3. Merge the entries in `dashboard/github-managed-dashboards.yaml` into the existing top-level `lovelace:` section. Do not add a second `lovelace:` key.
4. run Home Assistant's configuration check and restart Core.
5. Verify all three YAML dashboards before deleting the old UI-controlled copies.

The Admin dashboard is registered with `require_admin: true`. The Display Panel is intentionally hidden from the main sidebar and is designed to be opened directly on the NSPanels.

