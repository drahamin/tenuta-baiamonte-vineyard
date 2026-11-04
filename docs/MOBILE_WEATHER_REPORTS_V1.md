# Per-metric station report clocks v1

Frozen source/DTO candidate for review, 2026-11-04. Not released or activated
by this document. Existing `/weather` without the selector is unchanged.

Request: `GET /api/baiamonte_mobile/v1/weather?projection=station-reports-v1`.
Only that single query key/value is accepted. The existing `weather` capability
and session/role policy apply; no new capability, flag, HA route, entity selector
or permission is introduced. Existing Admin, Enologist, Worker and Viewer weather
readers can use this opt-in. Revocation is checked before cache/source access.

Response extends the existing `baiamonte.direct-site.v1` envelope with
`projection="station-reports-v1"`,
`projection_contract="baiamonte.mobile-weather-reports.v1"`, and `reports`:

```json
{
  "reports": {
    "contract": "baiamonte.mobile-weather-reports.v1",
    "estate_id": "11111111-1111-4111-8111-111111111111",
    "timestamp_basis": "home_assistant_state_report",
    "metrics": {
      "temp_c": {
        "value": 20,
        "unit": "celsius",
        "reported_at": "2026-11-04T11:59:00Z",
        "clock_field": "last_reported",
        "data_age_seconds": 60,
        "quality": "current"
      }
    }
  }
}
```

The example is synthetic and shortened to one metric. Actual successful reports
contain the fixed twenty metric keys below. Existing `weather` (including its
current values, forecast and advisories) and `freshness` remain separate.

| Metric | Canonical unit |
| --- | --- |
| `temp_c`, `feels_like_c`, `dew_point_c`, `soil_temp_c` | `celsius` |
| `humidity_pct`, `leaf_wetness_pct`, `soil_moisture_pct` | `percent` |
| `vpd_kpa` | `kilopascals` |
| `pressure_hpa` | `hectopascals` |
| `wind_kph`, `wind_gust_kph`, `gust_max_today_kph` | `kilometres_per_hour` |
| `wind_direction_deg`, `wind_direction_10m_deg` | `degrees` |
| `rain_mm` | `millimetres` |
| `rain_rate_mm_h` | `millimetres_per_hour` |
| `solar_wm2` | `watts_per_square_metre` |
| `uv_index` | `index` |
| `sensor_battery_v`, `sensor_capacitor_v` | `volts` |

Every metric has exactly `value`, `unit`, `reported_at`, `clock_field`,
`data_age_seconds`, `quality`. Values are finite bounded numbers or null. Zero
is retained. Report dates are aware UTC ISO timestamps or null; ages are
nonnegative integer seconds or null. Quality is `current` through 600 seconds,
`stale` afterward, or `unavailable` with null value/time/age/clock field.

`clock_field` identifies the actual HA field used: `last_reported`, falling back
only when absent to `last_updated`, then `last_changed`. These mean HA report,
state/attribute update, or state change respectively. They are not proof of a
physical sampling instant. Invalid/naive/date-only/future clocks are not replaced
by another sensor, local timezone, cache refresh, request or capture time.
A future clock rejected at cache capture cannot age into valid evidence later.
Age/quality are recomputed at every read; cached `quality=current` is not trusted.

There is no shared `observed_at` across the metrics. Different sensor report ages
remain different. Do not use the newest report to mark every weather field fresh,
or label the forecast, condition, derived rain flag or unqualified fields current
from one qualified metric. Native may label each **Reported**, **Updated**, or
**Changed** according to its clock field. Source freshness stays distinct from
successful API loading and from the database-read completion metadata.

Evidence is attached to the existing server-owned HA refresh/cache. It reads no
additional entity, recorder history, service, network endpoint or database table.
Only the selected exact commissioned `DEFAULT_GW2000_ENTITIES` binding qualifies
for a metric, with a matching source entity ID, known declared physical unit and
the existing tested unit conversion. UV index is explicitly dimensionless.
Renamed/fuzzy resolver aliases are not silently attested; their legacy values
may remain visible but qualified report metadata stays unavailable until the
binding is reviewed. A read-only existing-cache inspection found 19 of 20 resolved
site metric bindings match commissioned defaults; leaf wetness is a nondefault
resolved alias. This is binding evidence, not live acceptance of every metric.

Raw IDs, friendly names, arbitrary attributes, errors, credentials and provider
objects are not serialized. Estate is server-owned and must match the evidence.
Database fallbacks and wrong/unqualified evidence produce unavailable reports,
never fabricated history. Non-finite and Boolean numeric sensor states are also
rejected before legacy weather serialization.

Remaining gates: independent source/native DTO review, full regression and
package/release qualification, then authenticated report acceptance. Existing
grants, sessions, diagnostic windows, station configuration and collectors'
schedule remain unchanged. No new permission approval is needed for these
timestamps on the already-authorized station weather values.
