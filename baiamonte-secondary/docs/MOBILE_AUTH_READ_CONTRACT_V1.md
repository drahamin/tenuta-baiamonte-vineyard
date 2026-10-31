# Baiamonte iPhone real-user read contract v1

Status: **implemented, staged and disabled**. The controller routes are wired but
fail closed while `mobile_auth_enabled=false`; migration 006 has not been applied
to production.

## Identity and authorization

The phone does not choose a username or role. It opens the website's existing
Home Assistant login in `ASWebAuthenticationSession`. The website completes the
existing HA OAuth/PKCE flow, resolves the pre-provisioned `app_users` row, and
re-checks that the account is enabled. The server returns the role from that row.
Email addresses never create, match, elevate, or link accounts.

Resolution uses the verified HA user ID against an already bound `app_users`
row. It never uses a client-selected username and never defaults another person
to David. Unknown or unbound HA identities are denied. Role changes, disables
and session revocations are re-evaluated by the backend on subsequent requests.

The only native client is `com.cantinabaiamonte.vineyard`, with callback
`baiamonte-vineyard://auth/callback`. The callback carries a one-time code and
state, never a website session cookie or HA token. A client-generated PKCE S256
verifier binds an intercepted callback to the initiating phone.

## Proposed exchange

1. The app creates a random 43-128 character PKCE verifier and S256 challenge.
2. `GET /erp/auth/mobile/start` validates the exact client and callback, starts
   the normal HA OAuth flow, stores the PKCE challenge plus hashes of both a new
   mobile state and the exact HA OAuth state, and puts the mobile state in a
   short-lived `Secure`, `HttpOnly`, `SameSite=Lax` browser-binding cookie.
3. After HA succeeds, the existing callback requires both the HA OAuth state and
   browser-binding cookie to match the same transaction. It binds that transaction
   to the authenticated, enabled local user and redirects to the exact app callback
   with `code` and `state`.
4. `POST /erp/auth/mobile/exchange` atomically consumes the five-minute code after
   verifying state and PKCE. It returns a random opaque bearer token once.
5. The server stores only SHA-256 of the token. The token expires after one hour
   and has the single scope `replica.read`.
6. `POST /erp/mobile/v1/session/revoke` revokes it immediately and idempotently.

Authorization codes and bearer tokens are redacted from application logs and are
sent only in request bodies/headers that are absent from access-log URLs.
Responses use `Cache-Control: no-store`. Starts are globally bounded, an
authorization code locks after five failed exchanges, and authenticated data
requests are atomically limited per mobile session to the configured 10–600
requests per minute (production default 120).

## Read surface

Bearer authentication is accepted only on these new endpoints:

- `GET /erp/mobile/v1/me` — `username`, `display_name`, server-side `role`, expiry.
- `GET /erp/mobile/v1/status` — sync success time, source time, data age and error.
- `GET /erp/mobile/v1/catalog` — role-specific mobile winery-object names only.
- `GET /erp/mobile/v1/records?object=<permitted>` — estate-, role-, object- and
  field-filtered winery records.

The mobile read layer is deny-by-default even when an object exists in the wider
website replica. V1 permits only `wine_lots`, `cellar_containers` and
`vintage_summaries` for viewers; operators and admins additionally receive
`harvest_lots` and `fermentation_observations`. Each object has an exact scalar
field allowlist, every row must contain the configured matching `estate_id`, and
unknown or nested payload values are omitted. Missing measurements remain
null/unknown.

WhatsApp events/intake, vehicle presence, hospitality, payroll, finance, camera,
alerts, tasks, admin payloads and every unlisted object are denied even to an
admin holding this initial token. Status exposes freshness only, without raw sync
errors, snapshot IDs or whole-replica counts. A mobile token is never accepted on
browser ERP, command, camera, admin, sync, payroll, cellar-write, or device-control
routes.

The authenticated user may have the server-side role `admin`; that role is
returned by `/me` but does not enlarge this first token beyond `replica.read`.
The separately staged administrator capability matrix defines later explicit
capabilities without wildcard authorization.

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
