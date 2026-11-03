# Isolated mobile read projection — 2026-11-03

Source-only, unregistered and not a release artifact. Base current main
`c61e4a1bf4f32aebedb88d2dbf522012995fe6c4` (Vineyard1.11.86). No changes to
existing routes, auth/session code, role grants, PHP/WordPress, credentials,
database schema/rows, HA/Power Guard/device controls, native Swift or phone.
Do not package these added files as the immutable1.11.86 release.

## Ownership and contract selection

Native owner01a19281 is active on build28/phone work. This task owns only
`app/domains/mobile_energy_projection.py`, its tests and a sanitized fixture;
no duplicate Swift implementation. Native owner received a backend coordination
message identifying the solar-forecast/clock discrepancies and this exact
isolated checkout, without requesting any phone/release action.

The old `DIRECT_SITE_PARITY_API_V2.md` is a design handoff, not the current
native DTO. It describes `history` plus top-level `units`, but the existing
`MobileEstateEnergySnapshot` actually decodes `metrics` and
`series:{units,points}` under `baiamonte.mobile-telemetry.v1`. This projection
uses that existing native shape, including `ok`, rather than silently changing
the active direct-site `baiamonte.direct-site.v1` response. No endpoint imports
or calls this new module. Fixtures are synthetic, not private HA payloads.

## Concrete implementation

`project_energy_read` is pure: supplied reporting-view records in, sanitized
DTO out; no network, SQL, files, credentials, background work or commands.

- Only records explicitly tagged `ro_estate_energy_observations`, exact
  canonical estate boundary, five closed fields/units W/%/kWh. Grid,
  generator, HA entity IDs, evidence/private blobs and record revisions cannot
  leak into the output. Revisions are not converted through floating point.
- Preserves existing direct permission: admin AND energy capability. The
  separate ERP operator role is not implicitly admitted. Identity parameters
  must eventually come from the existing server-validated session, not request
  JSON or caller headers.
- 24h/7d only; at most20,000 input rows and289/337 output points. Sorts dated
  observations, preserves gaps in aggregation, never backfills current missing
  battery values from older rows, and keeps latest unaggregated current values.
  Equal-time field conflicts become NULL, not last-write-wins.
- Missing/invalid/NaN/infinite/Boolean values stay NULL; real zero is retained.
  SOC outside0–100 and negative PV/load/forecast values are rejected, not
  clamped. Positive battery watts mean discharge; negative means charge only
  after source-sign evidence is explicitly verified.
- Missing/date-only/invalid/future/out-of-range times are not measurements.
  Naive timestamps need an explicitly verified timezone. Ambiguous or missing
  DST wall times are rejected. No date is filled with now or a neighboring row.
- Measurement age and source-snapshot age stay distinct. Missing/old/future
  source clocks never imply current. Old valid data is explicitly stale;
  missing data is unavailable. Snapshot-generation mismatch fails the whole
  projection with `mobile_read_snapshot_changed`.
- Default schema/observation-clock/sign gates are closed and return unavailable.
  Caller-provided truth is not itself evidence: the future reader needs an
  independently reviewed source proof before setting them.

## Critical source discrepancies / limits

1. **Capture time is not sensor measurement time.** Migration132 defines
   `estate_energy_observations.observed_at` as DATETIME(6), but both existing
   writers in intelligence.py and utility_routes.py fill it using current UTC
   truncated to a minute. They do not persist each sensor's `last_updated`.
   Therefore the permitted reporting-view timestamp cannot automatically be
   treated as proof that every sensor measurement is fresh. This task neither
   calls those writers nor changes their schema. Observation-clock provenance
   remains a gate, not a live-data claim.
2. **Remaining solar forecast is not stored battery energy.** The writers fill
   `forecast_remaining_kwh` from `solar.forecast_energy_remaining`. Native
   source currently labels it "Remaining" and uses "kWh left" in battery
   summaries. No battery capacity/SOC multiplication or field renaming is
   invented here. Until consumer semantics are explicitly verified, this
   projection masks that field to NULL independently of battery availability.
   Native owner was notified. Re-enabling it needs an honest solar-forecast
   label or a separately reviewed true battery-energy source/DTO.
3. **Runtime schema access is not verified.** Source reporting manifest permits
   `ro_estate_energy_observations`; migration132 proves the underlying column
   definitions, not the current filtered view. No existing local13306 listener
   was found. Earlier SSH forwarding was administratively denied; no new tunnel,
   DB client, password copy, grant or forbidden underlying-table query was used.
   Current inspected flags are mobile read/schema enabled and remote-display
   disabled on1.11.86. Runtime view columns, read privileges, actual telemetry
   values and measurement freshness remain unverified.

## Source-grounded coverage map — not a parity/acceptance claim

| Area | Existing source / adapter | Exact gap / safe next step |
| --- | --- | --- |
| Battery/history | Permitted ro_estate_energy_observations; current direct `/energy` returns only solar summary with unknown freshness; native direct battery method deliberately returns unavailable | New pure projection+fixture prepared. No reader/route wiring. Prove schema/clock/sign and agree native DTO before any integration. Missing solar never gates valid battery fields. |
| Weather | Existing direct DTO allowlists current wind_kph/wind_gust_kph/rain_rate_mm_h and forecast separately; source describes home_assistant/database_last_known/cache | Native direct mapper currently drops wind/rain, labels generic direct_site_observation and may fall back to overall freshness timestamp. Preserve actual station measured/nearby/forecast provenance; unknown observation date cannot become fetch/cache date. Do not call weather/utility readers merely as diagnostics if they schedule refresh/persist observations. |
| Work | Existing direct `/work` returns bounded display tasks; ERP contract has tasks/activities/open/issues with revision/cursor/snapshot semantics | Direct read is only a subset. Native adapter's `revision=updated_at or read-only`, empty estateID and nextCursor=NULL are not ERP lossless-revision/pagination parity. No manufactured assignments or broadened worker role. |
| Review | Existing direct `/review` returns role-filtered alerts/issues/lab queue; ERP has admin queue/history datasets | Preserve actual capability/object gates; no approval controls or action URLs. Do not relabel these different datasets/counts as exact parity or widen enologist/admin scope to match an operator UI. |
| Cellar/history | Existing direct cellar/grapes summaries; reporting wine_lots/cellar_containers/vintage_summaries/harvest_lots available in source manifest | Direct summary is not full production history. Explicit current_container_id/lot links only; no fuzzy vessel-name join, financial fields or invented revisions/dates. |
| Enology | Existing fermentation_observations reporting object; native direct enology method returns notPermitted | No mobile reading route currently wired. Freeze exact container/lot relationship and typed Babo/temperature/density/Brix/pH units with real observation times before a reader. No notes-derived additions, doses or device commands. |
| Olives | Existing synthetic olive_harvests projection reads the explicit nonfinancial subset of olive_records | Source object is olive_harvests, underlying source is olive_records; no separate authoritative olive_harvests base table should be invented. Preserve NULL harvest/mill dates and distinguish planned estimates/recorded oil/packaged stock. Cost/payroll source data stays excluded. |
| Agronomy | Existing tasks, work_activities, vineyard_blocks and permitted ro_* phenology/scouting/maturity/treatment reporting sources | No direct generic agronomy dataset route. Use only closed, reviewed read fields; do not expose arbitrary source tables, assignment writes, treatment approvals or inferred prescriptions. |

No active v1 route, main.py, mobile_site_routes.py, remote_erp.py, configuration,
migration or release version is changed by this work. Existing PHP telemetry
and Work/Review contracts are not silently replaced. Runtime endpoint acceptance,
fresh source data, sync/outage recovery and physical native acceptance are NOT
proven by unit fixtures.

## Exact human/release gate

This source work needs no user secret or phone intervention to finish. Before
any integration/activation: independently review this module and actual native
DTO; verify the existing reporting view's permitted fields and measurement/sign
provenance via an authorized read-only source; resolve solar-forecast wording;
review a reader that uses one consistent permitted read without writes; then
obtain specific source release/route integration approval. Any schema/credential/
grant/new route/network or physical phone action remains a separate explicit
approval. Existing roles, ERP origin, direct-pilot Release gate and Power Guard
Observe/manual/stopped/watchdogfalse boundaries remain unchanged.
