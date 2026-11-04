# Weather projection — isolated implementation, not activation

Implemented a pure station-weather mapper from the reviewed 1.11.92 tree. It
does not import database, HA, settings, cache, refresh or network code. No main
registration, v1/v2 route, grant, identity/session policy, migration, dependency,
release manifest/version, website or production setting is changed. Publication
and installation authority for 1.11.92 does not authorize this new feature.

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
4. The v2 forecast array has no frozen per-item schema. Native's existing
   `MobileWeatherForecast` is not a Decodable wire DTO. The mapper deliberately
   returns `forecast:[]`; no forecast is promoted to a station observation or
   guessed wire format. Full detailed-weather parity is not claimed.

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

Next integration blocker is **not** the optional tasks validation. It is a
reviewed estate-scoped weather reader with real per-metric observation-clock
proof (or a redesigned per-metric DTO), plus a frozen forecast/client-envelope
mapping. Do not silently bless the legacy aggregate max-time/date fallback.
Once that source/DTO contract is reviewed, a separate default-off route/release
can be prepared. New sensitive access, grants and publication/deployment of
this unrelated software require their own applicable approval. Production stays
on 1.11.92 with tasks validation disabled.
