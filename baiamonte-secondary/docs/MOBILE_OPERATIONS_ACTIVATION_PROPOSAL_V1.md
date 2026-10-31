# Mobile operations activation and rollback plan v1

Status: fully implemented and tested in the local staging tree, but every new
feature is default off. No production database migration, credential, grant,
configuration change, release activation, or Vineyard restart has occurred.

## Implemented boundary

The website supports these bearer-only, estate-scoped routes. Identity and role
always come from the server-side `app_users` record; client-supplied identity or
role is ignored.

| Route | Server role | Output boundary |
| --- | --- | --- |
| `GET /erp/mobile/v1/weather` | viewer, operator, admin | measured temperature, rain rate, wind, observed time, explicit age/stale state |
| `GET /erp/mobile/v1/calendar` | operator, admin | title, date range, kind, status, priority and exact source record/revision |
| `GET /erp/mobile/v1/directory` | viewer, operator, admin | active display name, work role and derived team only |
| `GET /erp/mobile/v1/enology/readings` | operator, admin | dated, typed measurements for the exact tank and currently assigned lot |
| `POST /erp/mobile/v1/intake/reports` | operator, admin with `intake.submit` | create one immutable pending-review draft |
| `GET /erp/mobile/v1/intake/reports/{uuid}` | submitting actor with `intake.submit` | read that actor's status/result only |
| `POST /erp/mobile/v1/intake/reports/{uuid}/attachments` | submitting actor with `intake.submit` | upload one reserved JPEG, PNG or PDF |

Weather, calendar, directory, enology and intake each have an explicit default-
off feature flag. `intake.submit` is not part of the base `replica.read` scope.
It is granted only when explicitly configured, intersected with operator/admin,
stored per mobile session, and therefore requires a fresh HA mobile login.

The directory source is the purpose-built `SQL SECURITY INVOKER`
`ro_mobile_directory` view. It emits only estate ID, opaque SHA-256 row ID,
display name, work role, derived team, active state and update time. It does not
emit a login, HA entity/user ID, phone, email, messaging handle, presence,
location, payroll, finance or security data. Adding it advances the snapshot
contract from 1 to 2 and the reporting manifest from 61 to 62 objects. The
website accepts contracts 1 and 2 so a website-first rollout remains compatible
with the current Vineyard release.

Enology history validates the current tank-to-lot assignment. A mismatched lot
is rejected rather than combined with tank history. Missing observation dates
remain unknown. No route exposes notes, additions, prescriptions, tank modes or
controls.

## Intake durability and synchronization

Website migration 007 adds three private InnoDB tables:

- `mobile_session_capabilities`: exact capabilities bound to the hashed mobile
  token and deleted with the session.
- `mobile_intake_reports`: immutable canonical payload and SHA-256, actor and
  role snapshot, status/revision, hashed lease token, result and audit timing.
- `mobile_intake_attachments`: reserved digest/type/size, randomized private
  path and forwarding/deletion timestamps.

The private attachment directory must be an absolute path outside
`public_html`, mode 0700; files are mode 0600. Descriptors allow only SHA-256,
MIME, byte count and filename. Uploads are checked with `finfo`, size and digest;
inline bytes and unknown nested fields are rejected. A report is not leased
until every reserved file is present. Each report receives its own 256-bit lease
token, stored only as a hash.

Vineyard Operations polls the website outbound over the existing HTTPS origin
using a new, separate 256-bit HMAC key. There is no new inbound HA route, broad
HA token, SQL replication, source-table write, firewall, DNS or VPN change. The
source adapter revalidates:

- contract, UUID, estate, actor binding and operator/admin role;
- closed intake kind and typed measurement-unit enums;
- existence and exact snapshot-safe revision of every referenced entity;
- current tank-to-lot assignment; and
- attachment metadata, digest, magic bytes and size.

Accepted transport means the immutable evidence was durably stored as a
`mobile_intake_source_drafts` row with status `pending_review`; it does not mean
the report was applied to an operating record. Attachments are copied into the
existing HA private attachment store before acknowledgement. The website copy
is deleted immediately after the acknowledged accepted/rejected/conflict result.
An unacknowledged website copy hard-expires after 30 days and the report becomes
rejected with `attachment_retention_expired`.

Exact UUID retries with identical canonical content return the existing result.
Reusing a UUID with changed content is a collision. Revision or tank/lot changes
become explicit conflicts; no last-write-wins path exists. Corrections use a new
UUID linked to the original.

Human review is available at `/api/v1/mobile-intake`. Review requires an exact
expected revision and normal source write authorization; agronomy and enology
items also require the existing discipline approval. Review can set `approved`,
`rejected`, or `correction_required`, but deliberately returns
`domain_side_effects: []`. It does not create treatments, chemical doses,
inventory movements, tank actions, labor/payroll records, device commands or
power commands.

## Migrations and least privilege

The website migration must be executed by the already approved migration path,
not by broadening the runtime app user's privileges. The runtime user needs only
SELECT/INSERT/UPDATE/DELETE on the three new tables plus its existing access;
it receives no CREATE, ALTER, DROP, GRANT or access to excluded source data.

Vineyard migrations are additive:

- `232_mobile_intake_source_drafts.sql` adds the authoritative pending-review
  evidence queue.
- `233_mobile_directory_projection.sql` adds the minimized reporting view.

The intake HMAC key and key ID are app-scoped, stored mode 0600 on each host,
never returned through an API and never logged. They are distinct from snapshot,
camera and authentication credentials.

## Ordered activation gate

Activation remains blocked until final review approves the completed code and
an authorized migration path is available. Once approved, use this order:

1. Back up the website database, private config, active release link and private
   attachment directory metadata. Record counts and checksums for the current
   mobile/session tables.
2. Apply website migration 007 with the migration identity; verify schema,
   foreign keys, collation and that the runtime user has only the exact CRUD
   grants above.
3. Install the versioned website release while all new flags, capability grants
   and intake sync remain off. Verify existing login, replica and status routes.
4. Create one 256-bit base64url intake HMAC key through the owner handoff, write
   it to website private config mode 0600, and owner-paste the same value into
   Vineyard runtime config mode 0600. Do not copy an existing Studio key/token.
5. Create a fresh HA backup, apply source migrations 232/233, install the
   versioned Vineyard release and restart Vineyard Operations only. Do not
   restart Core, MariaDB, Power Guard, VPN, ADS-B or any device/power service.
6. Verify the first contract-2 snapshot: 62 unique objects, directory view
   present, no excluded fields, accepted timestamp and explicit data age.
7. Enable read flags one at a time and verify the role matrix. Then enable
   intake sync, intake feature and the exact `intake.submit` grant. Reauthenticate
   the approved mobile account so the capability is minted into a new session.
8. Run the staged acceptance tests below before real operational use.

## Acceptance tests

- Read role/estate boundaries for weather, calendar, directory and enology;
  verify missing values/dates remain unknown and freshness is explicit.
- Submit one synthetic no-attachment draft, retry the identical UUID, and verify
  one HA pending-review row and one website result.
- Reuse the UUID with changed content and verify collision rejection.
- Change a referenced revision and tank/lot assignment; verify conflict review,
  not an overwrite or reassignment.
- Submit a reserved test image; verify MIME/magic/size/hash checks, HA durable
  storage and immediate deletion of the website copy after acknowledgement.
- Stop only Vineyard Operations or disable its worker, submit offline, verify
  visible pending status, restore it, and verify one deduplicated delivery.
- Interrupt after HA storage but before website acknowledgement and verify retry
  returns the existing source draft without duplicate attachment or draft.
- Review one draft and verify the revision/audit change while every production
  domain table and all device/power state remain unchanged.

Do not claim persistent synchronization until a real refresh and the outage/
recovery acceptance test pass.

## Rollback

Before any real report exists: disable intake capability/feature/sync and all new
read flags, revoke the intake HMAC key, restore the previous website release and
Vineyard version, then drop only the verified-empty new tables/view through the
migration identity.

After any report exists: disable routes and worker, revoke the HMAC key, restore
the previous code versions, and preserve/export the audit queues and HA private
attachments under the approved retention policy. Do not drop evidence tables or
files. Contract-1 snapshots remain accepted by the website during rollback.

At all times keep Power Guard stopped with control mode Observe, boot manual and
watchdog false. No step authorizes power/device controls or changes to Core,
MariaDB service, VPN or ADS-B.
