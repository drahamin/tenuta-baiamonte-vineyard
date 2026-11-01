# Mobile field operations contract v1

Status: disabled source contract for review. No route, capability, migration, database grant, worker, or production flag is included.

Role-specific presentation and authorization requirements are defined in `MOBILE_ROLE_WORKSPACE_MATRIX.md`. A mobile workspace is a server-side restriction inside the existing role/capability ceiling; selecting it in the UI can never grant access.

## Existing canonical report path

Two-way reports continue to use `baiamonte.mobile-intake.v1` and the existing private attachment workflow. Reports are actor-bound, UUID-idempotent, estate-scoped, revision-bound and `pending_review` until Vineyard Operations validates them. Enology readings accept only the typed measurement codes and units already defined by `MobileFieldIntakeContract`. Attachments stay outside public directories and are forwarded only through the dedicated outbound HMAC lease.

This proposal does not add a second generic reporting endpoint or direct SQL. Corrections reference an earlier report UUID and never overwrite accepted evidence silently.

## Timeclock event contract

`MobileTimeclockContract` validates four closed event types: `clock_in`, `break_start`, `break_end`, and `clock_out`.

- Every event has a client UUID, client shift UUID, estate UUID, actual occurrence timestamp, client-created timestamp and IANA timezone.
- The authenticated server actor must already have a server-bound person ID. The client cannot nominate another person.
- `clock_in` creates the proposed shift identity and cannot claim an existing revision. Every later event requires the current lossless shift revision.
- Events are normalized to `pending_validation`; they do not open/close a shift, approve payroll, calculate pay, or create side effects on the website.
- Corrections create a new event UUID and may reference the earlier event UUID.
- Location fields are outside the contract. No covert GPS or background location collection is permitted.

The authoritative application must validate state transitions transactionally: one open shift per person, break start only while working, break end only while on break, and clock out only from an open shift. A supervisor correction is a separate audited domain action; it must not rewrite the submitted event history.

## Cellar operation contract

`MobileCellarOperationContract` is administrator-only in the initial source contract and validates four closed operation kinds:

- `racking.v1`: exact source and target containers, wine lot, transfer litres and expected loss litres.
- `product_addition.v1`: exact container, wine lot, catalog product, positive quantity, closed metric unit and reviewed reason.
- `filtration.v1`: exact container, wine lot, closed method, processed litres and expected loss litres.
- `tank_work.v1`: exact container, wine lot and one of sampling, mixing, lees stirring, cap management or cleaning; optional bounded duration.

Every referenced authoritative entity has an exact lossless expected revision. Extra or missing revisions fail validation. Racking cannot use the same source and target, and expected loss cannot exceed processed volume. Unknown payload fields, free-form doses, unsupported units and arbitrary operation names fail closed.

Validated operations remain `pending_validation`, with `inventory_committed=false`, `device_control=false`, and no side effects. Vineyard Operations must later recheck current revisions, vessel capacity, lot assignment, product catalog status, inventory availability and mass balance in one authoritative transaction. Conflicts require human review and a new UUID; there is no last-write-wins behavior or autonomous dosing.

## Still required before implementation

- Owner approval of exact routes, capabilities, roles, fields and lifetimes.
- Non-automatic MariaDB migrations for event/operation journals if the existing intake journal is not reused.
- Authoritative HA domain command handlers, not arbitrary SQL writes.
- Concurrency, offline/recovery, lost-response, conflict, correction and rollback tests.
- Mobile secure-storage and device-renewal implementation described in `mobile_routine_commands_device_renewal_proposal.md`.
- A staged end-to-end test proving one accepted event/operation is applied exactly once after an outage and a conflict is never overwritten.
