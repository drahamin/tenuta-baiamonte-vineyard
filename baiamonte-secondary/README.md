# Baiamonte secondary vineyard/winery GUI

This package is the isolated staging implementation for a website-hosted,
offline-capable reporting replica. Home Assistant (HA) remains authoritative.
It deliberately does **not** implement SQL replication and it never writes to
source tables.

## Trust boundaries

- HA exports only the approved reporting-object allowlist as a consistent,
  signed snapshot.
- The website stores snapshot rows in a private MariaDB database. A snapshot
  becomes visible only after one transaction atomically changes the active
  snapshot pointer.
- Website edits are immutable command envelopes. Each has a client-generated
  UUID, expected record revision, creation time, actor and payload.
- An HA-side worker pulls pending commands and invokes the existing Vineyard
  domain API. Results are acknowledged as `applied`, `conflict`, or `rejected`.
- Repeated UUIDs are deduplicated. Revision mismatches become conflicts; there
  is no last-write-wins path.
- Transfers carry both source and destination expected revisions in one
  command. The website validates that envelope, but HA rejects it until a
  specific authoritative atomic-transfer API is approved; it never falls
  back to generic SQL writes.

## Applied command scope

The outbound HA worker has deliberately narrow mappings:

- create a task through the existing task API, with the browser-generated
  record UUID retained for idempotent retry;
- update only a task's status through the existing task-status API;
- update the approved issue/decision fields through the existing issue API.

Each mapped update locks the authoritative source row, recomputes the same
revision used by the snapshot, and returns `conflict` before writing if it no
longer matches. Applied command UUIDs and results are stored in the existing
authoritative audit log in the same transaction, so a lost result response can
be retried without applying the edit again. Other objects, generic updates and
inventory transfers receive a terminal `rejected` result until an equivalent
domain API exists. No command path accepts a table name, SQL fragment, device
control or power action.

## Production boundary

Application code, configuration, logs and the replica database belong outside
the public document root. Only the narrow front controller and static assets
are web reachable. WordPress remains isolated and unchanged. The authorized
`/erp/app` interface reads only the private reporting replica; the legacy
public vineyard feed is not an input to it.

## Signed website releases

Website releases are code-only deterministic archives signed by the owner-held
Studio Ed25519 key. The repository-level `scripts/publish_release_pair.sh`
performs the intentional release-publication step; the private key never leaves
the Studio. The
website updater polls the pinned `cantinabaiamonte.com` manifest every 15
minutes, rejects redirects, oversized or modified artifacts, incompatible
contracts and all automatic schema changes, then stages and tests before an
atomic symlink swap. Failed live health checks restore the previous release.

Database migrations remain a separate, explicit approval path. A matching ERP
package is prepared once as part of the normal developer release publication,
before Vineyard Operations is installed. It is not a second owner command
after each installation; verified website installation is automatic.

## Required configuration

Copy `config/config.example.php` to a private, mode-0600 path outside every
document root. Provide secrets through environment variables or the private
configuration file. Never place a DB password, HMAC key, HA API key, SSH key,
or snapshot in a public directory.

The production object and camera allowlists are intentionally absent from the
public example. They belong only in the private production configuration after
their scopes have been approved and verified.

## Protocol

Snapshot request:

```http
POST /erp/sync/snapshots
X-Baiamonte-Key-Id: <id>
X-Baiamonte-Timestamp: <unix-seconds>
X-Baiamonte-Signature: sha256=<hex HMAC of timestamp + newline + raw body>
Content-Type: application/json
```

Commands are created only by an authenticated browser session with a CSRF
token. HA pulls them from `/erp/sync/commands` over the same signed protocol and
posts results to `/erp/sync/results`. Browser clients cannot mark commands applied.

## Verification

`tests/run.php` covers atomic snapshot activation, data-age metadata, missing
measurement dates remaining null, UUID deduplication, stale-revision conflict,
outage queuing/retry, and atomic inventory-transfer validation.

The authoritative HA-side transport is maintained in
`baiamonte-vineyard/app/remote_erp.py`; it is tested with the application suite.
