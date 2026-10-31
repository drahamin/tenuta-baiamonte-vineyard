# Mobile intake schema approval delta

Status: clarification and blocker record only. No migration, credential, grant,
configuration change, deployment or restart is authorized by this document.

## Earlier two-table approval

Migration 006 covered exactly these website tables for read-only mobile login:

1. `mobile_auth_transactions` — short-lived OAuth/PKCE handoff state, hashes,
   attempts, expiry and the bound local user.
2. `mobile_sessions` — hashed bearer token, local user, exact `replica.read`
   scope, rate window, expiry and revocation.

Those tables do not represent write capabilities or offline submissions. The
earlier approval cannot be interpreted to cover any table below.

## Current intake implementation: five approved tables total

Migration 007 proposes four website tables:

1. `mobile_session_capabilities`
   - Purpose: bind the exact optional `intake.submit` capability to one hashed
     mobile session token instead of treating an administrator role as a
     wildcard permission.
   - Stored data: `token_hash`, closed-enum capability name and grant time.
   - Why it is separate: capabilities are many-to-one, revocable with the
     session and must not enlarge the fixed `replica.read` scope column. Storing
     the capability only in configuration or trusting the client would not prove
     that the particular bearer received it.

2. `mobile_intake_reports`
   - Purpose: immutable website-side offline queue, UUID idempotency, actor and
     estate binding, revisions, lease state and read-your-submission result.
   - Stored data: report UUID, estate, actor ID/name/role snapshot, kind and
     dates, canonical payload and SHA-256, status/revision, hashed lease token,
     delivery attempts, bounded authoritative result and timestamps.

3. `mobile_intake_attachments`
   - Purpose: metadata and lifecycle for private evidence files reserved by a
     report; the bytes remain outside `public_html`.
   - Stored data: attachment/report UUIDs, SHA-256, MIME, byte count, original
   filename, randomized private path, upload/forward/delete timestamps and
   bounded cleanup retry state.

4. `mobile_intake_request_nonces`
   - Purpose: atomically reject replay of the dedicated intake HMAC requests.
   - Stored data: nonce hash, key ID, exact method/path, issued/expiry/claim
     timestamps. Expired claims are swept during authenticated intake traffic.

Vineyard migration 232 proposes one additional authoritative table:

5. `mobile_intake_source_drafts`
   - Purpose: durable HA-side immutable evidence awaiting human review. It is
     not a production treatment, inventory, tank, payroll or device record.
   - Stored data: report/estate/actor/kind, source and receipt times, canonical
     payload and digest, review status/revision, reviewer/time/note.

Migration 233 adds the separately approved minimized `ro_mobile_directory` view,
not a table. Directory activation remains independent of intake activation.

## Owner migration-path evidence and blocker

The repository documents two possible one-time owner mechanisms:

- `MOBILE_AUTH_ACTIVATION_RUNBOOK.md` specifies an owner-controlled MySQL option
  file, mode 0600 outside public roots, used once and deleted immediately.
- The older scoped cPanel helper creates a temporary migration user, grants only
  `CREATE, INDEX, REFERENCES` on `tenuoboe_baiamonte_erp`, applies the migration,
  and deletes the user in a trap and again on success.

The available local record does not prove which mechanism actually created any
production mobile-auth tables. It also contains conflicting historical reports
about whether jailed `/usr/bin/uapi` can currently reach its cPanel backend.
The runtime ERP database account is verified CRUD-only and must remain so.

Therefore the precise blocker is: there is no currently verified, authorized,
DDL-capable owner session available to this task. Existing Studio SSH and app
credentials are not authority to discover, copy or broaden database credentials.

The smallest supported owner action is one of:

1. Run the final reviewed migration through the host's authenticated cPanel/
   phpMyAdmin database owner session and return only the non-secret `SHOW CREATE
   TABLE`, row-count and `SHOW GRANTS` evidence; or
2. Place a purpose-limited temporary MySQL option file mode 0600 outside public
   roots for the existing SSH session, identify only its path, permit the one
   reviewed migration and verification, then delete it immediately; or
3. Have the host restore the scoped `uapi` database backend, after which the
   temporary-user helper must first be read-only validated and separately
   approved for the exact final migration.

No option permits printing a password, persisting a migration user, granting DDL
to the runtime app account or reusing credentials for another purpose.

## Non-schema review closure

The corrected implementation and tests now cover:

- current user/role/session/capability revalidation at lease and source accept;
- explicit HA reviewer/admin scope and author-own views;
- correction-chain ownership/estate validation;
- path/method/nonce-bound HMAC and atomic replay protection;
- durable conflict/rejection evidence delivery before website deletion;
- scheduled cleanup with retry/audit/health, not opportunistic-only deletion;
- ready-item leasing without incomplete-upload starvation; and
- bounded streaming uploads plus per-author/estate/pending/disk quotas.

The evidence and exact activation handoff are recorded in
`MOBILE_INTAKE_SECURITY_HANDOFF.md`. Independent review and the owner-controlled
DDL path remain mandatory; until both are cleared, all intake flags and workers
remain off and no intake HMAC key is created or handed off.
