# Mobile calendar, directory and intake activation proposal v1

Status: locally implemented contracts; read flags default off; no write route or
queue is registered. Nothing in this document authorizes production activation.

## Verified source inventory

- Calendar: Vineyard Operations already assembles a planning view from Home
  Assistant Calendar/Todo plus `tasks`, `work_activities`, planned treatments,
  `harvest_plans`, labor entries and `issues_decisions`. The existing website
  snapshot contains the four non-sensitive operational objects used by the
  staged mobile DTO: `tasks`, `work_activities`, `harvest_plans` and
  `issues_decisions`. The mobile DTO deliberately excludes external calendar
  descriptions/location, labor names/hours, treatment plans and record notes.
- Directory: the authoritative sources are administrator-owned
  `people_profiles`, HA Person state and separate WhatsApp address books. None
  is suitable for direct replication. A new purpose-built
  `ro_mobile_directory` projection is required. It contains only `estate_id`, a
  stable opaque row ID, `display_name`, `work_role`, `team`, `active` and
  `updated_at`; it contains no HA entity ID, username/user ID, presence,
  location, phone, email, messaging handle, payroll, finance or security data.
- Field intake: existing authoritative routes accept general intake files,
  worker work items, worker labor evidence, damage-review changes, treatment
  review requests and cellar readings. They have different side effects and do
  not form one safe offline mobile API. The staged contract therefore creates a
  review draft only; a source-side adapter must validate it and call an existing
  domain API only after review.
- Enology: existing `cellar_control_profiles` and
  `fermentation_observations` supply read history. The staged projection returns
  only Babo, temperature, specific gravity, Brix and pH with actual observation
  time, source record and exact revision. Missing dates remain unknown.
- Weather: `weather_observations` supplies the staged measured-current banner.
  It has explicit age/stale state and does not infer a condition or forecast.

## Read DTOs and role boundary

All routes use the existing one-hour mobile bearer, exact estate UUID and
server-resolved `app_users.role`. A client-supplied role or identity is ignored.
No wildcard capability exists.

| Route | Server role | Output boundary |
| --- | --- | --- |
| `GET /erp/mobile/v1/calendar` | operator, admin | title, date range, kind, status, priority and `{object,record_id,revision}` only |
| `GET /erp/mobile/v1/directory` | viewer, operator, admin | active work display name, work role and team only |
| `GET /erp/mobile/v1/enology/readings?container_id=…&wine_lot_id=…` | operator, admin | dated typed measurements for the exact container and currently assigned lot; no notes, additions, prescriptions or controls |
| `GET /erp/mobile/v1/weather` | viewer, operator, admin | measured temperature/rain rate/wind, observed time and data age |

The three new routes have separate default-off configuration flags. Calendar
uses existing replica objects. Directory cannot be enabled until the new source
projection is reviewed and added to the reporting manifest. Enology must not be
enabled until the exact profile fields and container/lot relationship have been
verified in a real snapshot.

## Proposed write contract (not registered)

Capability: exact `intake.submit`, intersected with server role operator/admin.
It is not included in the current `replica.read` token. Grant requires a fresh
HA login and a separately issued session containing `replica.read intake.submit`.

Routes:

- `POST /erp/mobile/v1/intake/reports` submits one immutable draft and returns
  `202 {report_uuid,status:"pending_review",deduplicated}`.
- `GET /erp/mobile/v1/intake/reports/{report_uuid}` returns only the signed-in
  author's status, revisions, rejection/conflict reason and authoritative
  record IDs. This provides read-your-submission behavior.
- `POST /erp/mobile/v1/intake/reports/{report_uuid}/attachments` accepts one
  bounded JPEG, PNG or PDF only after the JSON draft reserves its SHA-256,
  MIME and byte count. Maximum five files, 15 MiB each. Files remain in a
  private non-public directory and require an explicit retention decision.

Submission JSON:

```json
{
  "report_uuid": "UUIDv4; also the idempotency key",
  "kind": "field_observation|damage_report|work_report|cellar_note|agronomy_note|enology_reading",
  "estate_id": "exact configured estate UUID",
  "occurred_at": "RFC3339 timestamp with offset",
  "client_created_at": "RFC3339 timestamp with offset",
  "source_timezone": "Europe/Rome",
  "entities": {
    "block_id": "optional exact ID",
    "task_id": "optional exact ID",
    "work_activity_id": "optional exact ID",
    "container_id": "required for enology_reading",
    "wine_lot_id": "required for enology_reading"
  },
  "expected_revisions": {
    "container_id": "exact decimal revision string",
    "wine_lot_id": "exact decimal revision string"
  },
  "measurements": [
    {"code": "babo", "value": 18.1, "unit": "degree_babo"},
    {"code": "temperature_c", "value": 22.3, "unit": "celsius"}
  ],
  "instrument": {"name": "Hydrometer A", "identifier": null, "calibrated_at": null},
  "note": "bounded plain text",
  "attachments": [{"sha256": "64 hex", "media_type": "image/jpeg", "byte_count": 12345, "filename": "reading.jpg"}],
  "correction_of_report_uuid": null
}
```

The server adds immutable `author.username`, `author.server_role`, received
time and audit identity. The client cannot submit them. Every referenced entity
requires an expected decimal revision. The source adapter rechecks that the
estate owns each entity, that the selected wine lot is assigned to the selected
container, and that both revisions still match. A changed assignment or
revision produces `conflict`, preserving the draft for review; it never moves
the reading to another lot or tank.

Typed measurement units are closed enums. Enology accepts only Babo
(`degree_babo`), temperature (`celsius`), density (`specific_gravity`), Brix
(`degree_brix`) and pH (`pH`). Damage percentages use `percent`; rainfall uses
`millimetres`; wind uses `kilometres_per_hour`. A duplicate UUID with the same
canonical body returns the original result. The same UUID with different bytes
is a collision and is rejected.

The raw submission is immutable. Corrections create a new UUID linked through
`correction_of_report_uuid`; they never overwrite the original reading. The
author sees `local_draft`, `pending_upload`, `pending_review`, `accepted`,
`rejected` or `conflict`, and the existing authoritative history plus clearly
labelled pending submissions remain distinct.

## Proposed website persistence

Two additive private InnoDB tables, only after approval:

- `mobile_intake_reports`: report UUID primary key, estate, actor user ID,
  actor role snapshot, kind, source/received timestamps, timezone, canonical
  payload SHA-256, immutable payload JSON, status, expected revisions JSON,
  authoritative result JSON, revision, lease timestamps, created/updated time.
  Unique `(estate_id,report_uuid)` and actor/status indexes.
- `mobile_intake_attachments`: attachment UUID, report UUID foreign key,
  SHA-256, MIME, byte count, private randomized path, upload/forward/ack times.
  Unique `(report_uuid,sha256)`.

The website app user receives only the exact CRUD privileges required on these
two tables; no DDL and no access to source tables. Vineyard Operations polls a
dedicated HMAC route outbound, leases pending reports, validates the actor role
again, and posts accepted/rejected/conflict results. It then invokes an existing
domain service; it never executes client-provided SQL.

## Non-side-effect guarantee

Submission does not approve a treatment, calculate or recommend a chemical
dose, apply an inventory movement, change a tank mode, create payroll/labor
hours, control a device, or change power. A work report is evidence for review,
not proof of time or payment. An enology reading records measurement evidence,
not an addition, transfer, prescription or control instruction.

## Exact approval requested before activation

Approve or reject this complete boundary:

1. Add the privacy-minimized `ro_mobile_directory` source view and increase the
   remote reporting manifest/contract with only that view.
2. Enable the three read flags and expose the exact read routes above to their
   listed server roles.
3. Add token capability `intake.submit` for operator/admin only, the two private
   queue tables, three intake routes, HMAC lease/result routes, and an app-scoped
   HMAC secret stored 0600 on each host.
4. Permit the six intake kinds and typed units exactly as listed, with HA-side
   entity/revision/relationship validation and pending review only.
5. Choose attachment retention (recommended: delete website copy immediately
   after authoritative acknowledgement; hard-expire unacknowledged copies after
   30 days) and authorize private encrypted-at-rest storage if attachments are
   required.
6. Authorize a Vineyard-only versioned release/restart after a fresh backup. No
   Core, MariaDB, Power Guard, VPN, ADS-B, device or power restart/change.

## Test and rollback gate

Before activation: database and config backup; migration dry run; unit tests for
roles, estate boundary, typed units, author spoofing, idempotent retry, UUID
collision, stale revision, stale tank/lot mapping, immutable correction,
attachment MIME/magic/size/hash, and excluded side-effect fields. Then run an
isolated synthetic website-to-HA cycle, an offline submit/retry, a conflict,
and an outage/recovery cycle. Verify data age and pending state in the app.

Rollback before real reports: disable flags, revoke the intake HMAC, restore the
previous versioned website release and Vineyard version, then drop only the two
new empty tables. Once reports exist, disable routes and archive/export the
audit queue under the approved retention policy; do not drop it.
