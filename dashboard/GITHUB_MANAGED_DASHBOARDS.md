# GitHub-managed Home Assistant dashboards

The repository is the authoritative source for four Home Assistant dashboards:

- `baiamonte-vineyard/dashboards/vineyard-overview.yaml` — the full estate and vineyard overview.
- `baiamonte-vineyard/dashboards/display-panel.yaml` — a simplified, touch-friendly NSPanel interface.
- `baiamonte-vineyard/dashboards/ipad-panel.yaml` — a larger touch dashboard for the dedicated `ipad` account.
- `baiamonte-vineyard/dashboards/admin.yaml` — admin-only service, network, power, update, and diagnostic views.

Home Assistant registers them once under `lovelace: dashboards:`. The intended URLs are:

- `/vineyard-overview`
- `/vineyard-display/home`
- `/vineyard-ipad/home`
- `/vineyard-admin/system`

## Safe migration

1. Back up `/config/configuration.yaml` and the existing UI-controlled dashboards.
2. Copy the dashboard files to `/config/baiamonte_dashboards/`.
3. Merge the entries in `dashboard/github-managed-dashboards.yaml` into the existing top-level `lovelace:` section. Do not add a second `lovelace:` key.
4. run Home Assistant's configuration check and restart Core.
5. Verify all four YAML dashboards before deleting the old UI-controlled copies.

The Admin dashboard is registered with `require_admin: true`. The Display Panel and iPad dashboard are intentionally hidden from the main sidebar and are opened directly on their assigned devices.

For the dedicated iPad, sign in once as `ipad`, open `/vineyard-ipad/home`, then choose **Profile → Default dashboard → Baiamonte iPad**. Home Assistant stores that start-dashboard choice for the device; the managed installer intentionally does not rewrite Home Assistant user-profile storage. Use Guided Access or the Home Assistant app kiosk settings if the device should remain locked to this dashboard.
