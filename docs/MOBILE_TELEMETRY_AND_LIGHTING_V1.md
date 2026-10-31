# Native mobile Energy, Etna and lighting plan v1

Status: read-only Energy/Etna implementation frozen behind separate default-off
feature flags. Lighting is design-only and cannot be activated from this patch.

## Verified live sources

Energy history already exists in the permitted replica object
`ro_estate_energy_observations`. The latest inspected row was observed at
2026-10-31 22:38 UTC and contained battery 61%, battery discharge 266.8 W,
estate load 196.3 W, solar input unknown, and forecast remaining 0 kWh. A real
zero is preserved; an unavailable value remains null.

The live sanitized HA status also verified the following commissioned sources:

- battery bank SOC, power, remaining energy, voltage, health, online pack count
  and time-to-empty sensors;
- estate load and main-power sensors;
- Growatt input power and daily-energy sensors;
- overnight requirement, target, coverage and readiness sensors.

At inspection time the battery/estate sensors were available. Growatt solar
input power was explicitly unavailable. The app must display that as
Unavailable, never 0 W.

Mount Etna data already comes from the HA-owned official-source integration and
the permitted synthetic `ro_etna_status` record. It covers INGV communications,
VONA, VAAC, Civil Protection, seismic events, bulletins and webcam references.
The mobile API never polls those sources independently.

## Read routes

- `GET /erp/mobile/v1/energy?range=24h|7d`: operator/admin; flag
  `mobile_energy_enabled`; existing `replica.read` only.
- `GET /erp/mobile/v1/etna`: viewer/operator/admin; flag
  `mobile_etna_enabled`; existing `replica.read` only.

Both routes are bearer-only, estate/snapshot scoped, and return contract
`baiamonte.mobile-telemetry.v1`. Energy accepts only the optional closed `range`
query. Etna accepts no query fields. A snapshot change during assembly returns
409 `mobile_read_snapshot_changed`; denied roles return 403
`mobile_role_not_permitted`; malformed filters return 422
`invalid_mobile_telemetry_request`.

Energy returns at most 289 points for 24 hours or 337 points for seven days.
Each value carries a fixed unit, observation timestamp and
`current|stale|unavailable` quality. Series points preserve null gaps and are
marked `observed|partial|unavailable`. Battery power is positive while
discharging and negative while charging. No generator, grid, inverter setting,
control state or arbitrary entity is published.

Etna recomputes freshness at request time from `expires_at`; it does not trust
an old stored `fresh=true`. When expired, the current summary is nulled and the
seismic list is empty. Source timestamps remain available with `stale` quality
so the app can explain why no current status is shown. It must say that no
all-clear can be inferred and direct the user to official authorities.

## App views and gates

- Add Energy to the operator/admin navigation only after `/me` returns one of
  those roles and the Energy route succeeds. Use gauges for battery SOC and
  current load, plus line charts for battery SOC, battery power, estate load and
  solar input. Render nulls as gaps/Unavailable.
- Add Etna for viewer/operator/admin. Show the status cards only when
  `fresh=true`; otherwise show a prominent stale/unavailable panel and no
  current alert colour.
- Preserve source time and data age on both screens. A 409 discards the page and
  retries once from the beginning. A 403 removes the view for the session.
- Do not infer Lighting, Entry, Camera, Commands, Directory, Location, Finance,
  Payroll, Security or Power access from the admin role.

## Lighting discovery and approval boundary

The live registry has 54 enabled `light.*` entities:

- 30 browser-screen pseudo-lights — permanently excluded;
- 16 Eufy camera/security lights — permanently excluded;
- eight Legrand HomeKit entities used by the existing HA lighting dashboards.

The entity/device registry still has generic Switch 1–8 names and no area
assignment, but the active `ipad-panel.yaml` and `display-panel.yaml` dashboards
consistently provide the physical labels below; historical dashboard copies
agree:

| Entity | Existing HA label |
|---|---|
| `light.switch_1_lightbulb` | Kitchen overhead |
| `light.switch_2_lightbulb` | Warehouse |
| `light.switch_3_lightbulb` | Toilette |
| `light.switch_4_lightbulb` | Palmento |
| `light.switch_5_lightbulb` | Patio |
| `light.switch_6_lightbulb` | Patio strip |
| `light.switch_7_lightbulb` | Kitchen sink |
| `light.switch_8_lightbulb` | Fox Den overhead |

This is the exact proposed ordinary-light allowlist. Browser-screen pseudo-lights
and all Eufy camera/security lights remain permanently excluded. No switch,
power, pump, machinery, gate, generator, inverter, battery, security or fire
entity is included.

Lighting still requires separate action-time approval and a new
step-up `light.control` capability. The final command contract is restricted to
exact approved `light.*` IDs and `on|off` only. It must include a command UUID,
desired state, expected observed state/timestamp, actor, issued time and a
30-second expiry. The website rechecks the current enabled role and capability,
deduplicates by UUID, audits enqueue/result, and never accepts a service/domain
or entity supplied outside the fixed allowlist. Vineyard Operations refuses
expired or stale-state commands, invokes only `light.turn_on` or
`light.turn_off`, reads the resulting state back, and records conflict/failure
instead of retrying a stale command. No arbitrary HA service route is permitted.

No light or other device was toggled during discovery. Power Guard, pumps,
machinery, security/fire devices, Core, MariaDB and VPN were untouched.
