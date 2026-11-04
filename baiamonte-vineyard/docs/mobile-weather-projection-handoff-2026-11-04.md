# Weather compatibility 1.11.93 — local package, not deployment

Prepared a local 1.11.93 package from the deployed 1.11.92 tree, verified equal
to public main 6f4df194. The pure mapper does not import database, HA, settings,
cache, refresh or network code. Existing v1 weather serialization now uses its
bounded forecast mapper; no new v1/v2 route, grant, identity/session policy,
migration, dependency, website or production setting is introduced. Existing
source reads/refresh cadence remain unchanged. Publication and installation
authority for 1.11.92 does not authorize this different software package.

## Source and DTO discrepancies found before integration

1. `display_data.py` constructs the live display `observed_at` from the maximum
   update timestamp across station entities, or today's date if none exists.
   Neither proves a shared measurement time for every metric. Its cache
   `refreshed_at`/`age_seconds` describe fetching, not observation age. The mapper
   must not relabel either as measurement evidence.
2. The existing database fallback reads `weather_observations`, whereas the
   v2 handoff mentions `weather_daily` plus the reviewed current station source.
   Daily totals/averages do not establish current rate/temperature. This mapper
   accepts only a separately qualified `weather_observations` input; it does
   not create a reader or assume current authorization for a new route.
3. Native `MobileWeatherBanner` expects temperature/rain/wind typed objects
   and required `stale_after_seconds`; its source/data-age fields live inside
   `weather`, while the v2 handoff places freshness under top-level `source`.
   Those optional native fields can be absent, but a full v2 client adapter
   still needs to consume the new envelope. No client contract is changed here.
4. Resolved forecast representation from existing native source:
   `DirectSiteGateway.mobileWeather()` already maps exactly datetime, condition,
   temperature, templow, precipitation, precipitation_probability and wind_speed
   into `MobileWeatherForecast`. Retain those seven wire names and seven-row
   bound. Unknown scalar values are null, not invented. Unknown/date-only/naive
   validity times cannot be represented by that UI and are omitted, never given
   a synthetic midnight. No new user choice or forecast schema is needed.

## Minimal useful integration

The existing HA source read now carries provider-declared forecast units as
internal metadata on its existing bounded rows. Only declared Celsius, mm and
km/h yield typed numbers; unsupported/absent units remain null (no guessed
conversion). This metadata and private entity IDs never enter the mobile DTO.
No extra HA entity/service query or credential is introduced.

The existing native UI already renders forecasts separately when its station
record is unavailable. Keep the existing available/current object envelope so
that authorized forecasts remain usable; return observed_at null for the HA
aggregate max-time/date fallback, and unknown freshness/stale rather than cache
time as measurement time. A database-last-known timestamp is retained only if
it already includes an explicit timezone. Existing naive historical values stay
unknown. This may intentionally show measurement unavailable instead of a
misleading current station banner. Actual legacy safe metric values remain
present; the native additional-readings view is unchanged. This is a conservative
v1 compatibility fix, not full v2 parity or per-metric measurement-clock proof.

## Implemented behavior

- Existing weather role ceiling only: admin/enologist/worker/viewer with an
  already-present weather capability. No broader operator role or grant.
- Canonical requested estate UUID plus explicit row estate/object boundary.
  Trusted adapter qualification is mandatory and defaults false: permitted
  columns, estate scope, observation-clock and shared-metric-clock proof, and
  explicit measured/nearby provenance. Evidence is not an HTTP parameter.
- Aware observation times only; missing, date-only, naive, invalid and future
  times stay unknown. No timezone reinterpretation or cache/fetch fallback.
- Typed Celsius, mm/h and km/h values; zero preserved, unknown/boolean/nonfinite
  and out-of-bound values null. Rain accumulation never substitutes for rate.
- Source freshness and last-success timestamps stay separate from measurement
  time; old observations cannot become current merely because fetch succeeded.
- No condition inference, notes/advisories, raw HA entity IDs, coordinates,
  treatment advice, physical controls or cross-object joins. Input not mutated.

## Essential verification and next gate

Focused projection tests cover sensitive-field stripping, estate/object and
existing role/capability boundaries, default evidence gates, real zero/nulls,
measurement provenance and stale clocks. No production queries, refreshes,
captures, exhaustive suite or service interruptions were needed.

The source-clock gap no longer blocks this minimal version: the answer is
explicitly unknown/stale, not another collection/validation exercise. Full v2
measurement parity can follow later. Essential changed-path weather/auth checks
passed 77 tests in 0.77s; no exhaustive full suite or production capture. Local
release metadata and runtime manifest are separately checked before freeze.

Next release gates: source/package review, then explicit publication of this
software-only 1.11.93 candidate to the public Vineyard repository, normal CI and
merge, and one separately approved guarded Vineyard-only update with a fresh
1.11.92 app-only backup. Keep every diagnostic window blank, restore the actual
prior auto-update policy and verify health/runtime identity. No new mobile
grant, phone install, tasks validation, website activation, destructive restore
or physical/device control is included. Production is unchanged at this point.
