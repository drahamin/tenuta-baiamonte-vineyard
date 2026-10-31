# Baiamonte iPhone real-user read contract v1

Status: **staged and disabled**. No route in this document is registered in
`public/index.php`, and migration 006 has not been applied to production.

## Identity and authorization

The phone does not choose a username or role. It opens the website's existing
Home Assistant login in `ASWebAuthenticationSession`. The website completes the
existing HA OAuth/PKCE flow, resolves the pre-provisioned `app_users` row, and
re-checks that the account is enabled. The server returns the role from that row.
Email addresses never create, match, elevate, or link accounts.

The only native client is `com.cantinabaiamonte.vineyard`, with callback
`baiamonte-vineyard://auth/callback`. The callback carries a one-time code and
state, never a website session cookie or HA token. A client-generated PKCE S256
verifier binds an intercepted callback to the initiating phone.

## Proposed exchange

1. The app creates a random 43-128 character PKCE verifier and S256 challenge.
2. `POST /erp/auth/mobile/start` validates the exact client and callback, stores
   only the challenge and a hash of a random state, and starts the normal HA login.
3. After HA succeeds, the website binds the transaction to the authenticated,
   enabled local user and redirects to the exact callback with `code` and `state`.
4. `POST /erp/auth/mobile/exchange` atomically consumes the five-minute code after
   verifying state and PKCE. It returns a random opaque bearer token once.
5. The server stores only SHA-256 of the token. The token expires after one hour
   and has the single scope `replica.read`.
6. `POST /erp/mobile/v1/session/revoke` revokes it immediately and idempotently.

Authorization codes and bearer tokens must be redacted from application and
access logs. Responses use `Cache-Control: no-store`. Mobile authentication and
data routes are rate limited separately from browser routes.

## Read surface

Bearer authentication is accepted only on these new endpoints:

- `GET /erp/mobile/v1/me` — `username`, `display_name`, server-side `role`, expiry.
- `GET /erp/mobile/v1/status` — sync success time, source time, data age and error.
- `GET /erp/mobile/v1/catalog` — permitted replica object names only.
- `GET /erp/mobile/v1/records?object=<permitted>` — filtered replica records.

The implementation delegates status/catalog/records to the existing
`ReplicaService`; it does not query excluded source tables. Missing measurements
remain null/unknown. A mobile token is never accepted on browser ERP, command,
camera, admin, sync, payroll, cellar-write, or device-control routes.

## Activation prerequisites

- owner approval for the two-table migration and the disabled-to-enabled config change;
- an app build using the exact client ID, callback scheme, PKCE, Keychain storage,
  bearer redaction, and explicit sign-out/revoke;
- server routes wired behind the exact allowlist above, with no fallback to cookies;
- migration backup and rollback script verified on staging;
- tests for replay, expiry, disabled user, wrong client/callback/verifier, route
  confinement, revoke, and real `david` identity response;
- staged end-to-end login and read verification before any write API is considered.

Rollback disables mobile auth first, revokes all mobile sessions, then removes the
two tables only after confirming the app no longer calls the endpoints. Existing
HA browser sessions, passkeys, snapshots, WordPress, and Vineyard Operations are
unchanged.
