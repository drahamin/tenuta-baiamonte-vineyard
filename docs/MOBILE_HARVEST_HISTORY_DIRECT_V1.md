# Direct-site crop history v1

Frozen candidate for review, 2026-11-04. Implemented/tested in source staging;
not packaged, released or activated. It performs no source writes.

Request: `GET /api/baiamonte_mobile/v1/records?object=harvest&projection=harvest-history-v1&dataset=grapes`.
`dataset` is exactly `grapes`, `vintages`, or `olives`. Optional integer
`from_year` and `to_year` default to 2023 and the current Europe/Rome estate
year, respectively. Require `2023 <= from_year <= to_year <= current estate year`.
Only these five query keys are accepted, once each. No caller-selected estate,
limit, cursor, identifier, source object or SQL is accepted.

Authorization: Admin AND existing `records` AND a separate explicit
`harvest.read` session grant AND `mobile_harvest_history_enabled=true`.
The flag defaults false; the new capability is only an Admin role ceiling,
not an automatically issued grant. Worker, Viewer and Enologist are denied.
All checks precede source reads. Current identity policy/session revocation is
checked on every request. Existing sessions and legacy records are preserved.

Envelope:

```json
{
  "contract": "baiamonte.direct-site.v1",
  "projection_contract": "baiamonte.mobile-harvest-history.v1",
  "projection": "harvest-history-v1",
  "object": "harvest",
  "dataset": "grapes",
  "estate_id": "11111111-1111-4111-8111-111111111111",
  "filters": {"from_year": 2023, "to_year": 2026},
  "complete": true,
  "items": [],
  "source": {
    "basis": "reported_source_records",
    "date_basis": "source_calendar_date",
    "timestamp_basis": "unknown"
  },
  "freshness": {
    "generated_at": "2026-11-04T12:00:00+00:00",
    "source_generated_at": null,
    "data_age_seconds": null,
    "stale": true
  }
}
```

Each selected dataset is a complete single-statement SQL snapshot, bounded to
1000 source rows. Overflow returns 503 rather than a truncated successful read.
Three independent requests do not assert a shared cross-dataset generation.
No row revision, observation clock, or successful-sync date is invented.

`grapes` item:

```json
{
  "id": "22222222-2222-4222-8222-222222222222",
  "vintage_year": 2025,
  "season_id": "33333333-3333-4333-8333-333333333333",
  "variety_id": "44444444-4444-4444-8444-444444444444",
  "variety_name": "Nerello Mascalese",
  "harvest_date": "2025-09-30",
  "source_type": "estate_harvest",
  "reported_weight_kg": 100,
  "reported_crate_count": 0
}
```

The source is `harvest_lots`, joined to exact estate-qualified `seasons` and
`grape_varieties` IDs. IDs are canonical source UUIDs. Estate and purchased
fruit stay distinguishable through the stored `source_type`; no source type is
inferred. `harvest_date` is the DATE portion of the source DATETIME, preserved
as its stored calendar date; it is not converted to UTC or presented as a
verified physical collection timestamp.

`vintages` item:

```json
{
  "key": {"vintage_year": 2025, "variety_name": "Nerello Mascalese"},
  "reported_grapes_kg": 2825,
  "reported_wine_l": 1640,
  "evidence_status": "recorded"
}
```

The source is `vintage_summaries`. Its actual key is
`(estate_id,vintage_year,variety_name)`; with estate fixed by the envelope, the
remaining exact key fields are returned structurally. There is no made-up UUID
or revision. Variety text is preserved, not silently normalized into another
variety. The stored evidence status remains a source label, not fresh approval.
Reported wine volume is not automatically clean finished wine or bottled output.

`olives` item:

```json
{
  "id": "55555555-5555-4555-8555-555555555555",
  "record_year": 2025,
  "record_date": "2025-10-10",
  "mill_date": "2025-10-11",
  "reported_olives_kg": 100,
  "reported_oil_l": null,
  "reported_yield_pct": null
}
```

The source is `olive_records`, with exact source UUID, estate and record year.
Dates are source DATE values (`YYYY-MM-DD`) or null, never synthesized from year,
receipt or sync time. An olive row does not establish a milling-to-harvest lot
relationship; absent linkage is not inferred from date, weight or nearby rows.

Numeric fields are finite nonnegative numbers or null. Zero remains zero;
missing oil or wine output does not become a derived yield. Names, source type
and evidence status are source strings or null. No source notes, attachments,
document references, worker names/hours, finance fields or planning predictions
are read or returned. Invalid/cross-estate/duplicate source identities, wrong
year boundaries, invalid numbers/dates and oversized results fail closed with
503 `mobile_reporting_source_unavailable`. Invalid filters return 422; disabled
feature returns 404; existing auth failures remain 401/403.

Do not add summary and lot rows together: they can describe the same harvest.
Keep reported summary figures, dated receipts and purchased fruit separate.
No clean-wine loss, bottle conversion, counterfactual yield or model training
claim is made by this read contract.

Remaining gates: independent source/native DTO review; package/release checks;
explicit production flag and `harvest.read` approval for the intended existing
Admin identity; authenticated source/response and phone acceptance. No flag,
policy, source record or session has been changed in production.
