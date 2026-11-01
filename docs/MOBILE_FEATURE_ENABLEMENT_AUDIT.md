# Native mobile feature enablement audit

Status: 2026-10-31 server/source audit. Production is unchanged by this
document and the accompanying Work/Review patch.

The approved account's current server identity is HA-bound `admin`; the native
session scope is `replica.read`. Role and token capability remain separate
gates. The current token's staged `intake.submit` capability does not enable
intake while the feature and sync switches are off.

| Feature | Backend route | Live flag / role | Native state |
|---|---|---|---|
| HA login/profile | `/mobile/v1/me` | mobile auth on; any bound enabled role | Live, HTTP 200 observed |
| Replica freshness | `/mobile/v1/status` | `replica.read` | Live, HTTP 200 observed |
| Winery catalog/records | `/mobile/v1/catalog`, `/records` | viewer gets lots/containers/vintages; operator/admin also harvest/fermentation | Live |
| Weather | `/mobile/v1/weather` | flag on; viewer/operator/admin | Live, HTTP 200 observed |
| Calendar | `/mobile/v1/calendar` | flag on; operator/admin | Live, HTTP 200 observed |
| Directory | `/mobile/v1/directory` | flag off; viewer/operator/admin if separately enabled | Intentional hold |
| Enology history | `/mobile/v1/enology/readings` | flag on; operator/admin | Live, HTTP 200 observed |
| Work | `/mobile/v1/work` | proposed: operator/admin, estate scoped | Frozen patch; not live |
| Review | `/mobile/v1/review` | proposed: admin, estate scoped | Frozen patch; not live |
| Energy | `/mobile/v1/energy` | proposed: separate flag; operator/admin | Frozen read-only patch; not live |
| Etna | `/mobile/v1/etna` | proposed: separate flag; viewer/operator/admin | Frozen official-cache patch; not live |
| Lighting | no route | exact eight-light allowlist plus `light.control` step-up | Fixture map verified from HA dashboards; design only, awaiting separate activation approval |
| Intake context/submission | `/mobile/v1/intake/*` | exact `intake.submit` plus operator/admin plus feature flag | Intentional hold: feature off |
| Intake dispatch | `/sync/mobile-intake/*` | dedicated HMAC plus sync flag plus Vineyard worker | Intentional hold: both workers off |
| Commands | no native route | would require explicit `commands.enqueue` step-up | Unbuilt; not granted |
| Camera stills | no native route | would require explicit `camera.still`; existing browser flow is separate | Unbuilt; not granted |
| Location | no approved native contract | none | Unbuilt; not granted |
| Payroll/finance | explicitly outside mobile policy | none | Forbidden |
| Device/power controls | explicitly outside mobile policy | none | Forbidden |

## App navigation rules for the view owner

- Show Work only after `/me` returns role `operator` or `admin`; handle 403 as
  unavailable and 409 by discarding cursors and refreshing page one.
- Show Review only for role `admin`; do not infer access from
  `intake.submit`.
- Show Energy only for operator/admin after the feature route succeeds. Show
  null telemetry as Unavailable and keep chart gaps; never coerce null to zero.
- Show Etna for viewer/operator/admin, but render an alert/status as current
  only when the response says `fresh=true`. Expired cached alerts must not keep
  their current colours.
- Do not show Lighting until the exact fixture allowlist and a separate
  step-up control grant are deployed. Admin alone is insufficient.
- Do not expose Entry/Submit while field intake is off, even if `/me` lists
  the staged capability.
- Do not synthesize camera, command, directory, location, payroll, finance,
device, lighting or power tabs from the admin role.
- Render source state/data age on Work and Review. `available=false` is an
  explicit empty/unavailable state, not proof that there are no records.
- Preserve revision strings and opaque cursors exactly.

## Intake acceptance still required before activation

The fresh iPhone session and existing read views prove authentication and
read runtime only. Intake activation still requires a client-side context and
offline retry/conflict test, private attachment/retention verification, and an
outage/recovery test. No current result proves those behaviors.
