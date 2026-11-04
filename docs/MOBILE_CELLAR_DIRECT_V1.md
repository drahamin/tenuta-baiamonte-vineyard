# Direct-site current cellar assignments v1

Frozen DTO for native review, 2026-11-04. Implementation tested locally; not yet
released or production-qualified. Observation history is outside this slice.

Request: `GET /api/baiamonte_mobile/v1/records?object=cellar&projection=cellar-links-v1`.
Backend path: `/api/v1/mobile/records` with those same query parameters.
Only these two query fields are accepted, once each. No vintage, limit, cursor,
container name, entity ID, or caller-selected estate is accepted. This is the
complete active-container inventory across all currently assigned vintages,
bounded to 100 containers and 1000 joined source rows. Exceeding either boundary
returns 503 rather than a partial inventory.

Authorization is unchanged: existing `records` session capability AND the existing
role-specific `cellar` object permission (Admin or Enologist), with current identity
policy/session revocation checked on every request. No new capability, grant,
credential, HA proxy path, or control endpoint is introduced. The absence of
`projection` preserves the original scalar direct-site v1 response exactly.

Response:

```json
{
  "contract": "baiamonte.direct-site.v1",
  "projection_contract": "baiamonte.mobile-cellar.v1",
  "projection": "cellar-links-v1",
  "object": "cellar",
  "estate_id": "11111111-1111-4111-8111-111111111111",
  "complete": true,
  "source": {
    "assignment_basis": "wine_lots.current_container_id",
    "timestamp_basis": "unknown"
  },
  "items": [{
    "id": "22222222-2222-4222-8222-222222222222",
    "code": "T1",
    "name": "Tank one",
    "container_type": "tank",
    "material": "steel",
    "capacity_l": 1000,
    "location": "Cellar",
    "status": "in_use",
    "link_status": "single",
    "wine_lots": [{
      "id": "33333333-3333-4333-8333-333333333333",
      "code": "N-2025",
      "name": "Nerello",
      "vintage_year": 2025,
      "stage": "aging",
      "variety_summary": "Nerello",
      "reported_volume_l": 635
    }],
    "observations": [],
    "observation_status": "unavailable_container_observation_provenance_unverified"
  }],
  "freshness": {
    "generated_at": "2026-11-04T12:00:00+00:00",
    "source_generated_at": null,
    "data_age_seconds": null,
    "stale": true
  }
}
```

All IDs are canonical UUID strings from the source tables. `items[].id` is the
container ID; `wine_lots[].id` is the wine-lot ID. The sample is synthetic.
Text fields are strings or null. Capacity and reported volume are finite,
nonnegative numbers or null; zero is preserved. `vintage_year` is an integer.
`link_status` is `unassigned`, `single`, or `multiple`, based on the number of
explicit current lot assignments. Multiple lots remain individually identified;
the server never selects one winner, sums their volume, or asserts tank fill.
Do not use a lot ID as a container ID or vice versa.

Source is one bounded SELECT over `cellar_containers`, `wine_lots`, and `seasons`.
Every join and projected row is estate-qualified. A lot belongs to a container
only when its stored `current_container_id` equals that exact container ID.
Missing/cross-estate season, malformed or duplicate lot IDs, conflicting source
rows, invalid numbers, and oversized results fail closed with 503
`mobile_reporting_source_unavailable`. Unsupported filters return 422.
Normal session failures retain the existing 401/403 behavior.

This is current record attribution, not evidence of historical residence or a
measurement clock. `reported_volume_l` comes from `wine_lots.volume_l`; it must
be labeled reported, not measured now. No assignment revision is fabricated.
The response generation clock is not a source observation time.

The existing `fermentation_observations` schema has a lot ID and free-text vessel
name, but no explicit container ID. Its DATETIME clock has no per-row verified
timezone contract. `cellar_control_profiles` can identify a container but does
not prove which lot occupied it when a historical manual value was recorded.
Neither source qualifies for container-and-lot measurement history here.
Consequently every `observations` array is empty and its status is explicit.
The native client must not present that as zero readings or a successful history
sync, and must not infer a current measurement from the reported lot volume.

Remaining gates: native DTO review; scoped release checks; packaged source/hash
verification; post-deployment health and read-only projection qualification.
No new grant or permission approval is required for this opt-in within the
existing authorized cellar records scope. Lights and other read domains remain
separate work and are not authorized by this contract.
