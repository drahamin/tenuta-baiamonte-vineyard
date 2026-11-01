# Mobile field operations contract v1

Status: disabled source contract for review. No route, capability, migration, database grant, worker, or production flag is included.

Role-specific presentation and authorization requirements are defined in `MOBILE_ROLE_WORKSPACE_MATRIX.md`. A mobile workspace is a server-side restriction inside the existing role/capability ceiling; selecting it in the UI can never grant access.

## Existing canonical report path

Two-way reports continue to use `baiamonte.mobile-intake.v1` and the existing private attachment workflow. Reports are actor-bound, UUID-idempotent, estate-scoped, revision-bound and `pending_review` until Vineyard Operations validates them. Enology readings accept only the typed measurement codes and units already defined by `MobileFieldIntakeContract`. Attachments stay outside public directories and are forwarded only through the dedicated outbound HMAC lease.

This proposal does not add a second generic reporting endpoint or direct SQL. Corrections reference an earlier report UUID and never overwrite accepted evidence silently.

The existing implementation already exercises the first usable end-to-end workflow: submit a typed report, reserve and stream a verified private attachment, keep it out of dispatch until complete, lease both through the outbound authoritative worker, and persist `accepted`, `rejected`, or `conflict`. Website evidence is deleted only after the authoritative service confirms durable evidence. No new production work is required for that path in this source branch.

`accepted` at this transport boundary means that Vineyard Operations durably received the immutable report and evidence as a `pending_review` draft. It does not mean that a reviewer approved the observation or that any domain record was changed. The existing review `PATCH` records only `approved`, `rejected`, or `correction_required` plus its audit event and explicitly returns `domain_side_effects=[]`. A separate reviewed domain command is still required for any operational change.

The source privacy boundary now excludes every `mobile_intake_draft` attachment from the generic attachment catalog. Preview, download, and the dedicated report-evidence list allow only the immutable author, an administrator/internal service, or a reviewer with the matching agronomy/enology approval. Same-estate viewers, unrelated operators, and other authors receive 403. This closes the activation blocker but does not activate intake.

The author's durable receipt is the website report status (`pending_review`, transport `accepted`, `rejected`, or `conflict`) together with the HA-owned `/mobile-intake/mine` review lifecycle. A dedicated review surface and decision propagation now exist only as source-disabled components; activation must not describe the flow as review-complete until they are wired and tested in the release.

## Minimum first-report activation bundle (source-disabled)

The first complete flow is deliberately one kind and two people: website/mobile user `david` with the server role `admin` may submit an `enology_reading`; HA user `sebastian`, with Operations access and the saved role `Agronomist & Enologist`, independently reviews it. David cannot review his own submission. No other author, reviewer, report kind, timeclock event, cellar operation, inventory mutation, payroll action, device control or power control is included.

The proposed reviewer panel is in `baiamonte-vineyard/app/static/proposed/`. It is responsive on phone and desktop, shows the typed measurements and private evidence, requires a note for every decision, and labels the item `RECEIVED FOR REVIEW · NOT APPLIED`. The proposed route and outbox implementation are in `app/proposed/`; neither is imported by the running application. A review transaction changes only the immutable draft lifecycle and inserts one idempotent outbound receipt. Its response freezes `business_application_status=not_applied` and `domain_side_effects=[]`.

The website receipt keeps three independent states:

- transport: the existing `status` (`accepted` means durably received by HA);
- human review: `review_status` (`pending_review`, `approved`, `rejected`, or `correction_required`);
- business application: always `not_applied` in this bundle.

The phone must display all three and must never relabel an approved report as an applied tank reading. A changed retry for the same decision UUID/report is a collision; an exact retry is an idempotent success.

Already-defined schema prerequisites are website migrations 006 and 007 (`mobile_sessions`, `mobile_session_capabilities`, `mobile_intake_reports`, attachments and HMAC nonces) and HA migrations 232 and 233 (`mobile_intake_source_drafts` plus durable ingest result). The new schemas are proposals only: `baiamonte-vineyard/db/proposed/234_mobile_intake_review_outbox.sql` and `baiamonte-secondary/db/proposed-mobile-intake-review.{mysql,sqlite}.sql`. They are outside both migration runners and have not been applied.

Retention stays unchanged: website evidence is private, bounded to 15 MiB per file, deleted after HA confirms durable evidence, and otherwise swept at 30 days; HA keeps the accepted private evidence under the existing attachment policy. The review receipt contains metadata and the review note, never copied image/PDF bytes. Before activation, the HA evidence-retention duration and deletion job must be explicitly confirmed because this bundle does not invent a new HA deletion policy.

Activation requires all of the following in one reviewed release: database backups; successful rehearsal of both proposed migrations and their rollback; exact configured identities `david` and `sebastian`; Sebastian's discipline role check; the new HMAC review path added to the closed allowlist; the source-disabled route/outbox worker and reviewer assets explicitly wired; the website receipt service wired into the HMAC route and author-scoped report status; and tests proving submit/upload, HA-offline queueing, independent approval, exact retry, collision rejection, phone receipt, private evidence denial, and no domain side effect. A flag flip by itself is insufficient.

## Disabled durable domain mailbox

`MobilePendingDomainService` now supplies the same durable request/result lifecycle for timeclock and cellar DTOs without registering a route. It stores immutable validated requests in `pending_validation`, revalidates the originating account, session and dedicated capability before a 90-second lease, and records only an authoritative `accepted`, `rejected`, or `conflict` result.

The worker contract names closed application handlers: `vineyard.timeclock.record_event.v1` and `vineyard.cellar.apply_operation.v1`. These are domain-service boundaries, not table names. The website service never writes source or replica records. An accepted cellar result is rejected unless the authoritative application returns record IDs, lossless revisions, one transaction UUID, `inventory_committed=true`, and `atomic=true`. Timeclock results cannot claim inventory effects. Removed capabilities are rejected before dispatch, and UUID retries with changed content fail closed.

The Vineyard source now includes those two real handlers in `app/mobile_domain_handlers.py`, still unimported by the runtime. The timeclock handler locks the bound worker and shift, validates the exact event transition/revision, writes the labor shift and event journal in one transaction, and leaves payroll unapproved. The cellar handler locks the same reporting rows used to calculate revisions and performs the lot/container/product checks and operation write in one database transaction. Its authoritative receipt is stored in that transaction; a boolean from a fixture is not treated as proof by the handler itself. Exact terminal result retries replay without another transition, and an authority change after an authoritative commit cannot rewrite the recorded success.

The proposed SQLite and MariaDB schemas are deliberately named `proposed-mobile-domain-workflow.*.sql`; production bootstrap and migration tooling do not load them. Dedicated `timeclock.submit` and `cellar.operations.submit` grants remain separate from current mobile token capabilities.

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
- Review and explicit execution of the proposed MariaDB journal/capability migration.
- Authoritative application handlers for the two named domain contracts, not arbitrary SQL writes.
- Dedicated outbound HMAC lease/result routes and a worker configuration flag, both default-off.
- Concurrency, offline/recovery, lost-response, conflict, correction and rollback tests.
- Mobile secure-storage and device-renewal implementation described in `mobile_routine_commands_device_renewal_proposal.md`.
- A staged end-to-end test proving one accepted event/operation is applied exactly once after an outage and a conflict is never overwritten.

Exact activation approval must name the accounts/workspaces receiving each dedicated capability, the two routes and HMAC key scope, migration checksum, lease interval, authoritative handler versions, feature flags, backup/rollback steps and staged acceptance identities. Approval of this source contract alone does not authorize those changes.
