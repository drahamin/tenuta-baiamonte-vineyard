# Remote read profiles — candidate 1.11.85

Source-only security boundary, not an activated service. Production remains
1.11.84. No policy file, identity, key, grant, database migration, hostname,
Cloudflare application or origin exposure is provisioned by this change.
The display gateway option remains false by default. The existing native-phone
gateway, Core integration and local display/label services are unchanged.

## Explicit routes and data contract

| Profile | Pages | JSON reads | Explicit resource grant |
| --- | --- | --- | --- |
| `label_device` | `/labels/tank/{container_uuid}`, `/labels/kiosk/{kiosk_uuid}` | `/labels/api/tank/{container_uuid}`, `/labels/api/kiosk/{kiosk_uuid}` | `tank_ids` AND `kiosk_ids`; kiosk's current tank must also be allowed |
| `field_reader` | `/field/` | `/field/api/tasks` | `task_ids` |
| `pos_reader` | `/pos/` | `/pos/api/catalog` | `catalog_ids` |

Each surface permits only its two exact static assets at
`/{surface}/assets/remote-read.js` and `remote-read.css`. Every page, asset and
read requires authentication. GET/HEAD only; no query arguments or request
bodies. There are no redirects or arbitrary upstream proxies. Encoded paths,
legacy token URLs, manifests, service workers, enrollment, TV/ADS-B/AIS,
cameras, general HA/WebSocket/admin APIs, communications, payroll, financial
administration, payments, sales, printing and device/power controls are denied.

All JSON has `read_only:true`, `offline_cache:false` and a server
`generated_at` response timestamp. This timestamp is NOT a measurement date.
Record dates remain their recorded values, including NULL. Naive source
timestamps are not relabeled as UTC.

Source/DTO discrepancies are explicit; this does not change the native v1/v2
parity contracts or claim full local GUI parity:

- **Labels:** `manual_label_v1` reads only the permitted tank's existing manual
  `cellar_control_profiles`, capacity/code/name/status from `cellar_containers`
  and active label binding. It does not reuse the full local label function,
  which also fetches legal/person data, inferred defaults, external sensor data
  and other history. Manual volume/contents can differ from a newer wine-lot
  record. This is an explicitly marked manual record, not a complete legal
  label or a live tank state. Full operational/legal parity is a separate data
  contract review, not a reason to silently widen this projection.
- **Kiosks:** UUID lookup checks active kiosk AND current tank grants; no legacy
  public token, notes, device enrollment or `last_seen_at` write. The existing
  local kiosk GET writes `last_seen_at`, so it is deliberately not called.
- **Field:** `assigned_task_read_v1` projects only explicitly listed `tasks`
  IDs, title/category/status/priority/due date/update date. No person identity,
  notes, labor rate/hours, timeclock or write workflow is returned.
- **POS:** actual selling catalog is `register_catalog_items`, NOT the general
  `products` table. `catalog_identity_read_v1` returns only approved IDs,
  names/SKUs/units/update dates, with `available_quantity:null` and
  `inventory_status:not_authorized`. Source stock is not current availability:
  the existing selling-stock calculation subtracts commitments from sales
  tables. Those financial reads are out of scope. No prices, VAT, customer,
  payment, checkout or receipt data is returned. A usable selling POS would
  need a separately approved inventory/transaction contract.

## Authentication and private policy

The connector-origin secret remains required but is NOT a device identity.
The request must also have exactly one `Cf-Access-Jwt-Assertion`. Verification
uses PyJWT 2.15.1 / cryptography, RS256 only, a policy-pinned HTTPS
`<team>.cloudflareaccess.com` issuer and that surface's exact application AUD.
JWT exp/iat/iss/aud/sub are required, expiry/future issuance checked, token
lifetime at most 24 hours. Unsupported headers (including jku/x5u/crit), weak
or ambiguous keys and forged/caller identity headers cannot grant access.

Public signing keys are fetched only from the configured issuer's fixed
`/cdn-cgi/access/certs`, with verified TLS, no proxy, redirects or stale-key
fallback, five-second socket timeout, 64KiB maximum body and at most16 keys.
Public-key service loss denies access. This prioritizes fail-closed isolation
over offline availability; concurrency/latency must be measured in a pilot
before deciding whether a separately reviewed bounded cache is appropriate.

`/data/remote-access-policy.json` is an owner-provisioned regular file, effective
process owner, mode0600, no symlink, at most64KiB. No file is created by startup.
It is reread for every request; missing/disabled/malformed policy denies all.
Duplicate JSON keys, profile ambiguities, duplicate host/AUD across apps,
wildcards, unknown roles/resources and noncanonical UUIDs are rejected.
Local policy revocation applies to subsequent requests; a request already
admitted can finish. Access-side JWT revocation alone does not invalidate a
previously signed assertion at this origin: also disable its local profile.

Policy schema1 has exactly `schema`, `enabled`, `issuer`, `applications`,
`profiles`. Each application key is `labels`, `field` or `pos`, with exactly
`host` and `audience` (Cloudflare's64-hex app AUD). Each profile has exactly:

- `principal`: exact verified JWT `sub`, never caller email/name/role;
- `device_id`: unique local identifier;
- `surface`, its exact fixed `role`, Boolean `enabled`, integer UTC-epoch
  `expires_at`;
- `resources`: exactly the resource-list keys in the table, canonical UUIDs,
  no wildcards, maximum128 IDs/list. Empty lists grant nothing.

This binds an authenticated principal to a device profile, NOT hardware by
itself. A copied bearer assertion can be replayed until expiry/revocation.
A shared human account does not identify one physical display. A supported,
dedicated per-device principal/authentication mechanism is an activation gate;
browser service-token header injection is NOT assumed. JWTs without a usable
verified `sub` fail closed; do not fall back to caller headers or guessed claims.

## Cache, failure and logging behavior

All responses (including assets/errors) use no-store/private, explicit Vary,
no-referrer, no frames, no camera/microphone/geolocation/payment permissions
and a self-only script/style/connect CSP with worker-src none. No inline
script, HTML injection, third-party resources or client bearer persistence.
The small UI polls every15s with an8s timeout, no redirect following, and clears
rendered data on auth/network failure, offline/hidden/pagehide. An old in-flight
response cannot restore data after a clear. DOM data may remain until the next
poll detects revocation; this is not an instantaneous remote screen wipe.
No localStorage/IndexedDB/offline fallback or service worker is installed.
Activation must verify a fresh/clean origin without a pre-existing controlling
service worker; CSP alone cannot revoke an old registered worker.

Port8103 disables Uvicorn access logs and proxy-header trust. UUID URLs are
resource identifiers, never bearer credentials. Assertions, keys and profile
values are not returned or logged by this gateway. Cloudflare/provider logging
and metadata retention remain separate activation checks, not a zero-retention
promise. This change never transports camera bytes.

## Exact activation gates and rollback

1. Finish independent code/security review and CI on a frozen source head;
   approve a separate Vineyard-only release deployment, verified fresh rollback
   backup and health/version/manifest checks. No Core restart is needed for
   these source files. No source merge/deployment is implied by this document.
2. Owner identifies one physical label pilot and its tank/kiosk UUIDs. Verify
   the supported device authentication and exact signed subject, issuer/AUD,
   credential expiry/renewal/revocation. Obtain action-time approval before any
   persistent device/origin secret, private policy or principal/resource grant.
   Field/POS need separately named humans/roles/resources and separate app
   audiences/hosts; none is chosen or granted here.
3. Cloudflare observer's read-only plan remains authoritative for rollout:
   `/Users/rahamin/Documents/Codex/2026-11-01/task-3/display-activation-plan.md`.
   Access was at Zero Trust onboarding, not verified application inventory.
   Do not accept onboarding/plan/terms or assume Chrome sign-in is approval.
   Prepare default-deny self-hosted Access with no Bypass/Everyone rule; prove
   denial before publication. Approve the exact app/grant and HTTP-only block.
4. Establish a bounded connector-to8103 origin path without publishing raw8101/
   8102, adding a broad HA route or altering the existing phone8184 tunnel.
   Origin reachability is UNVERIFIED. Any listener/network/public hostname/DNS
   change requires exact approval; do not enable merely because source exists.
5. Before owner acceptance, verify actual allow/deny matrix, cross-tank/kiosk,
   local+Access revocation, expiry, clean cache/worker state, reboot, WAN/JWKS
   outage/recovery, source dates/data agreement and mobile/desktop rendering on
   the single device. No persistent synchronization or outage acceptance claim
   is made by unit tests. Retain VPN throughout observation.

Rollback: disable the exact new hostname route and grants, disable its local
profile/gateway, restore the previous device URL. Restore the fresh Vineyard
backup only if needed; no schema migration/drop or data rollback is required.
Do not alter phone, ERP, Core, MariaDB, VPN, Power Guard or other services.

Primary reference: [Cloudflare JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/),
[official PyJWT package](https://pypi.org/project/PyJWT/). These describe JWT
verification, not an authorization to create any application or credential.
