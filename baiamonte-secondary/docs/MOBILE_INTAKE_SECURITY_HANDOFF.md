# Mobile intake security handoff

Status: code complete for independent review; production activation remains
blocked. No production intake schema, credential, flag, worker, cron entry, or
service restart was created while preparing this handoff.

The deployed mobile read release remains a separate no-schema release and is
not replaced by this branch. This full intake branch cannot be activated until
website migration 007 has created the token-capability and intake tables and HA
migration 232 has created the source-draft table.

## Closed review findings

- Submission, attachment upload, status reads, lease dispatch, and result
  acknowledgement all use the current token-bound user. Dispatch joins the
  current enabled user, unrevoked/unexpired session, exact `intake.submit`
  capability, and unchanged operator/admin role. Vineyard Operations performs
  an independent exact username-to-role allowlist check before source ingest.
  HA receipt authority is intentionally the configured exact username/role
  allowlist plus the website's capability/session attestation, which HA rejects
  when older than 180 seconds. It is not a fresh HA account lookup. The human
  review endpoints independently apply current HA ingress authorization.
- The full HA review queue and review action require administrator
  authorization. An authenticated author has a separate `/mine` view restricted
  to their current username. Agronomy and enology approvals retain their
  discipline gates and exact expected revision.
- Every outbound request is HMAC-bound to method, exact registered path, key
  ID, timestamp, 256-bit nonce, and compressed-body SHA-256. The website claims
  the nonce transactionally before routing and rejects replays.
- Only complete reports enter the oldest-ready queue. Incomplete earlier uploads
  cannot starve ready reports; expired 90-second leases are returned to the
  queue with a fresh one-time lease token.
- Website attachments are deleted only after HA has durably stored the draft
  and all evidence and explicitly returns `evidence_durable=true`. A lost result
  acknowledgement retries idempotently against the durable HA draft. Conflicts
  are stored as pending-review evidence before acknowledgement. HA attachment
  publication uses a mode-0600 same-filesystem temporary file, file `fsync`,
  atomic rename, and directory `fsync`; every idempotent retry reopens and
  rehashes all expected evidence before replaying a durable result.
- Uploads stream in 64 KiB chunks to a mode-0600 file outside `public_html`.
  MIME, magic, digest, declared size, 15 MiB file size, five-file report limit,
  per-author/estate pending counts and reserved bytes, and free-disk reserve are
  enforced before dispatch.
- Corrections use a new UUID and must reference the same author, estate, and
  intake kind on both website and HA.
- Retention is two phase. A durable delete request is recorded first; unlink
  failures retain metadata, back off, remain visible in the health endpoint,
  and are audited. The cleanup CLI deliberately continues running when intake
  and sync flags are disabled, so rollback does not suspend retention.

## Scheduled cleanup requirement

Activation must install a private cPanel cron entry at five-minute cadence for:

```text
/usr/local/bin/php /home/tenuoboe/apps/baiamonte-secondary/current/ops/mobile_intake_cleanup.php /home/tenuoboe/apps/baiamonte-secondary/config/config.php
```

The job must run as `tenuoboe`, write no secrets, and send output to an
owner-controlled private log or monitoring destination outside `public_html`.
Before enabling intake, deliberately stage one retryable cleanup failure and
verify `GET /erp/api/admin/mobile-intake-health` reports it, the next scheduled
run retries it, and the audit trail records both failure and success.

## Tested evidence

- PHP 8.0.30 full unit suite: pass.
- PHP 8.0.30 real HTTP router integration: pass.
- PHP 8.0.30 persistent replay concurrency regression: pass; two independent
  processes raced the same signed nonce and exactly one claim persisted.
- PHP 8.0.30 persistent quota concurrency regression: pass; two independent
  75 MiB reservations raced and only one persisted under the 100 MiB author
  limit.
- Focused Vineyard Operations source/review tests: pass.
- Website migration 007: executed successfully on disposable MariaDB 10.11.
- Vineyard migration 232: executed successfully on disposable MariaDB 10.11.
- Both SQLite test migrations execute in the PHP suites.

The suites cover capability gating, role change rejection, HA viewer/operator
queue denial, author-only status, correction ownership, ready-queue fairness,
lease expiry/retry, replay denial, exact persisted conflict replay, durable and
rehash-verified evidence acknowledgement, rejected-evidence quota accounting,
retention while disabled, bounded JSON reads, streaming and disk-pressure
limits, quota concurrency, and the default-off HTTP boundary.

## Exact activation handoff

After independent code review and a separate action-time approval:

1. Take the backups and counts specified in
   `MOBILE_INTAKE_SCHEMA_APPROVAL_DELTA.md`.
2. Use the owner-controlled DDL path to apply website migration 007 and HA
   migration 232. Do not grant DDL to either runtime user.
3. Verify exactly four website intake tables plus one HA source-draft table,
   their foreign keys, engines, collations, and narrow runtime CRUD grants.
4. Install the reviewed release with every intake flag and worker still off.
5. Create one dedicated 256-bit intake HMAC key through owner handoff; store it
   only in the two private runtime configurations and configure the exact JSON
   username-to-role allowlist.
6. Install and verify the cleanup schedule above.
7. Enable website intake/capability first, then the Vineyard outbound worker.
   Do not enable directory unless separately directed.
8. Run submit, retry, attachment, conflict, authority-revocation,
   outage/recovery, durable-ack, and cleanup-retry acceptance tests. Disable the
   worker and website intake flags immediately if any invariant fails.

Rollback disables the Vineyard worker, removes `intake.submit` from new mobile
sessions, disables website intake/sync flags, revokes the dedicated HMAC key,
and restores the prior release/config link. Evidence tables are retained for
review; they are not dropped during rollback. The cleanup schedule remains
enabled until its health endpoint reports no pending retention work.
