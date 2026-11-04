# Existing database-read completion metadata v1

Frozen candidate for independent source/native review, 2026-11-04. This additive
metadata applies only to existing no-projection `/records`, `/work` and `/review`
responses under `baiamonte.direct-site.v1`. It creates no route, data source,
record field, capability, identity-policy change, or diagnostic activation.
The exact cellar, lights and crop-history projection DTOs are unchanged.

Optional top-level field:

```json
{
  "read_status": {
    "state": "completed",
    "completed_at": "2026-11-04T15:00:00+00:00",
    "timestamp_basis": "database_read_completion",
    "sources": {
      "tasks": {"returned_count": 4, "limit": 50, "limit_reached": false}
    }
  }
}
```

The example is synthetic. `state` is exactly `completed`; `completed_at` is an
aware UTC timestamp taken after the existing authorized SELECTs finish.
`timestamp_basis` is exactly `database_read_completion`. It dates the successful
read, not a measurement, source update, sync, ingestion, model training, or
reporting snapshot generation. Native may label it **Loaded** or **Fetched**.
It must not label source data Live/current or infer item observation times.

`sources` contains only existing source objects actually authorized and read:

- `/work`: `tasks`.
- `/review`: the authorized subset of `alerts`, `issues`, `labs`.
- no-projection `/records`: the one authorized requested object.

Each entry has an integer returned count, the existing request limit (1–100,
default 50), and a Boolean `limit_reached` which is true when returned count
equals the limit. A limit hit leaves completeness unproved and should remain a
visible possible-incomplete-view warning. No total count or pagination guarantee
is invented. Separate Review queries do not prove one atomic cross-source
snapshot. Missing permission is not represented as an empty successful source.

The field is emitted only after the existing source reads succeed. Normal
401/403/422/503/500 behavior is unchanged; errors never carry a completed read
status. Existing arrays, field minimization, filters and row limits are unchanged.
An older client can ignore this optional metadata. A newer client must accept
its absence on older servers; absence does not mean the arrays are empty.

`freshness` remains independently conservative. Domain source clocks now use the
strict source-clock parsing: aware values normalize to UTC; date-only,
timezone-less, invalid and missing values have unknown source time/age. Future
aware clocks retain their source value for diagnosis but never have age zero or
current freshness. No local, CET or UTC historical writer timezone is guessed.

The separate `_as_utc` helper retains its explicit UTC session-table writer
semantics. Session issuance, expiry, audience, identity-version checks, grant
checks, revocation and authenticated exchange behavior are unchanged.

Remaining gates: independent source/native review; scoped and full regression;
release/hash qualification; native handling of optional completion metadata.
No new grant, flag, diagnostic window or source-data approval is required.
