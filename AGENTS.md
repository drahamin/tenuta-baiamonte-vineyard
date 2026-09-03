# Project operating notes

## Home Assistant deployment

- Use the configured SSH host alias `baiamonte-ha` for Home Assistant administration and add-on deployment.
- Refresh the add-on store with `ssh baiamonte-ha 'ha store reload --no-progress'` after publishing a new version.
- Update the installed add-on with `ssh baiamonte-ha 'ha apps update 0c04eef6_baiamonte_vineyard --no-progress'`.
- Verify the add-on with a narrowly filtered `ha apps info` result plus the add-on `/health` response and served asset version.
- Never print an unfiltered `ha apps info --raw-json` response because it includes protected add-on options and credentials.
- Prefer the current `ha apps` commands; `ha addons` is deprecated.
