# Mobile read authentication activation runbook

Status: preparation only. Do not execute production steps without the owner's
action-time approval for migration 006, release activation and the exact mobile
route/config scope.

## Fixed production scope

- database: existing private `tenuoboe_baiamonte_erp` only;
- new tables: `mobile_auth_transactions` and `mobile_sessions` only;
- existing app DB user remains `SELECT, INSERT, UPDATE, DELETE` only;
- no persistent `CREATE`, `ALTER`, `DROP` or grant change;
- no WordPress, HA, Vineyard Operations, firewall, VPN or device-control change;
- active release is read before staging and must still equal the reviewed base;
- new bearer authentication is accepted only for the four `GET` routes and the
  one revoke route in `MOBILE_AUTH_READ_CONTRACT_V1.md`.

## Backup and preflight

1. Record the exact active release target and configuration checksum without
   printing configuration contents:

   ```sh
   readlink /home/tenuoboe/apps/baiamonte-secondary/current
   sha256sum /home/tenuoboe/apps/baiamonte-secondary/config/config.php
   php /home/tenuoboe/apps/baiamonte-secondary/current/ops/website_preflight.php \
     /home/tenuoboe/apps/baiamonte-secondary/config/config.php
   ```

2. Create and verify a fresh hosting-provider/cPanel database backup and an
   archive of the active release plus private configuration. Store both outside
   public web roots. Record identifiers, sizes and SHA-256 values. Do not use the
   CRUD-only app account to claim a complete DDL-capable backup.
3. Restore the backup into isolated staging and run migration 006 there first.
   Verify both tables are empty and the existing ERP suite still passes.

## One-time migration

Use an owner-controlled database administration session. If the host supplies a
temporary MySQL option file, it must be mode `0600`, outside public roots, and
deleted immediately after use. Never put a password on the command line.

```sh
mysql --defaults-extra-file=/private/temporary-owner-mysql.cnf \
  tenuoboe_baiamonte_erp \
  < db/migration-006-mobile-read-session.mysql.sql
```

Verify exact shape and keep the application grant unchanged:

```sql
SHOW CREATE TABLE mobile_auth_transactions;
SHOW CREATE TABLE mobile_sessions;
SHOW GRANTS FOR CURRENT_USER();
SELECT COUNT(*) FROM mobile_auth_transactions;
SELECT COUNT(*) FROM mobile_sessions;
```

The application account must still report only `SELECT, INSERT, UPDATE, DELETE`.

## Release activation

1. Build the release from the currently reviewed production base, not from an
   older local package. Include the mobile classes, migration and route wiring.
2. Run PHP lint and the complete SQLite suite. Inspect the package manifest and
   confirm the private config, backups, credentials and database are absent.
3. Upload into a new versioned private release directory. Run preflight there.
4. Leave `mobile_auth_enabled=false`; verify ordinary ERP login and all existing
   authenticated reads still work, while every mobile route fails closed.
5. Atomically update the private config with exact client/callback/TTL values,
   then atomically switch the `current` release link. No service restart is used.
6. Verify one HA login from the test phone, `/mobile/v1/me` returns the real
   `david` mapping, and status/catalog/one permitted records request succeed.
   Verify an excluded object, every write route, a replay, expired code, expired
   token and revoked token are rejected. Revoke the test session.

## Rollback

1. Set `mobile_auth_enabled=false` atomically. This is the first containment step.
2. Revoke all issued mobile sessions with the owner database session:

   ```sql
   UPDATE mobile_sessions
      SET revoked_at = UTC_TIMESTAMP(6)
    WHERE revoked_at IS NULL;
   ```

3. Atomically repoint `current` to the recorded previous release and verify
   browser HA login, status, catalog and records.
4. Keep the two inert tables for incident review. Drop them only in a later,
   separately approved maintenance action after confirming no client calls them:

   ```sql
   DROP TABLE mobile_sessions;
   DROP TABLE mobile_auth_transactions;
   ```

The additive migration does not alter existing ERP tables, users, sessions,
snapshots, commands or audit records.
