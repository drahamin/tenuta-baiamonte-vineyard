# Mobile routine commands and device-bound renewal proposal

Status: source-only proposal. No production route, capability, database grant, credential, migration, or feature flag is activated by this document.

## Goal and boundary

The native app should read and submit routine vineyard records through the authenticated Baiamonte website API and its private MariaDB database without requiring Home Assistant to be online for each operation. The app must never receive database credentials or connect to MariaDB directly.

The existing website replica remains the read model. Routine edits are persisted immediately in the existing website `commands` journal, shown as pending, and later applied by Vineyard Operations through its authenticated local domain APIs. The replica is replaced only by a subsequent accepted source snapshot; the website must not fabricate an authoritative revision after accepting a command.

Device, camera, light, power, generator, inverter, network, security, finance and payroll operations are outside this proposal.

## Disabled-by-default routes

The following routes are registered only when both `mobile_routine_commands_enabled` and the required token capability are true:

- `POST /erp/mobile/v1/routine-commands`
- `GET /erp/mobile/v1/routine-commands?limit=1..100`
- `GET /erp/mobile/v1/routine-commands/{command_uuid}`

The POST contract is typed. The client does not choose an arbitrary database object, SQL operation or field name.

Common fields:

- `command_uuid`: client-generated UUID, reused for an exact retry.
- `kind`: one of the four closed values below.
- `record_id`: existing record UUID/ID, or a client UUID for task creation.
- `expected_revision`: required lossless decimal string for updates; forbidden for task creation.
- `client_created_at`: RFC 3339 timestamp with offset.
- `payload`: exact kind-specific object.

### `task.create.v1`

- Roles: exact approved administrator in the initial release.
- Existing worker mapping: `record.create` on `tasks`.
- Allowed payload fields: `title`, `category`, `status`, `priority`, `due_date`, `block_id`, `estimated_hours`, `notes`.
- Required: non-empty `title`.
- `expected_revision`: forbidden.

### `task.status.v1`

- Roles: exact approved administrator in the initial release.
- Existing worker mapping: `record.update` on `tasks`.
- Payload must contain exactly `status`.
- `expected_revision`: required.

### `issue.update.v1`

- Roles: exact approved administrator.
- Existing worker mapping: `record.update` on `issues_decisions`.
- Payload must be non-empty and may contain only `priority`, `decision_action`, `owner_text`, `due_date`, `status`, `closed_date`, `notes`.
- `expected_revision`: required.

### `cellar.reading.v1`

- Roles: exact approved administrator in the initial release.
- Existing worker mapping: `record.update` on `cellar_control_profiles`.
- Allowed payload fields: `babo`, `temp_c`, `observed_at`, `notes`.
- `observed_at` is required and must be RFC 3339 with an offset. At least one of `babo` or `temp_c` is required. Units remain Babo and degrees Celsius.
- `expected_revision`: required.

Viewer and operator tokens cannot submit commands in the initial release. Expanding operator permissions must be a separate reviewed policy decision rather than inheriting the broader role capability table accidentally.

## Command authorization and lifecycle

The proposed token capabilities are `commands.read` and `commands.enqueue`. They are granted only when the server feature is enabled and remain intersected with the current server-side user role on every request.

Routine command submission requires a valid device-bound local session but not a five-minute Home Assistant step-up. This is the explicit policy change needed for offline vineyard work. Sensitive capabilities such as `light.control`, `camera.still`, `admin.sync.rotate`, device control and power control remain absent from renewed sessions and retain their existing fresh-HA requirements.

The server maps each typed command to the existing `CommandService` representation, preserving:

- actor binding and enabled-user checks;
- UUID content deduplication;
- expected source revision;
- immutable payload comparison on retry;
- receipt and client timestamps;
- audit events;
- actor-scoped status reads.

States remain the existing closed set:

- `pending`: durably accepted by the website and awaiting the vineyard;
- `leased`: claimed by the outbound Vineyard Operations worker;
- `applied`: accepted by the authoritative domain API;
- `conflict`: expected revision did not match; requires human review and a new command UUID;
- `rejected`: policy or domain validation failed; requires correction and a new command UUID.

There is no last-write-wins path. A conflict response returns only minimized authoritative IDs/revisions and a stable reason. A rejected or conflicted command is never silently retried as changed content. Inventory transfers are not part of this first mobile contract.

When the vineyard is offline, the API continues to accept commands as `pending`. The app shows the local submission time, website receipt time, state, last successful replica sync and replica age. When the vineyard returns, the existing outbound worker leases and applies commands through local authenticated application APIs and posts the durable result.

## Device-bound local renewal

The current one-hour access token remains unchanged. Renewal avoids a full Home Assistant login for routine reads and commands while preserving a bounded proof established by an initial HA login.

### Enrollment

During a successful HA OAuth + PKCE mobile login, the app generates a non-exportable signing key in platform hardware-backed secure storage and a random 256-bit renewal secret. It sends the public key, a client-generated device UUID and only the SHA-256 hash of the renewal secret in the one-time exchange. The server never receives the private key and never stores the plaintext renewal secret. HA access and refresh tokens continue to be revoked after identity resolution and are not used for renewal.

The server stores a `mobile_devices` row containing the device UUID, user ID, client ID, public key, current renewal-secret hash, generation, creation time, last-used time, absolute expiry, idle expiry and optional revocation time. Device labels are optional local metadata and must not be accepted as authority.

### Lifetimes

- Access token: 1 hour, as today.
- Renewal idle lifetime: 24 hours since the last successful rotation.
- Renewal absolute lifetime: 7 days from the most recent full HA login/enrollment.
- Renewal challenge: 90 seconds, one-time.
- Fresh HA step-up for sensitive controls: unchanged at 5 minutes.

At idle or absolute expiry, routine server access requires a full HA login. Cached read-only data remains visible with its age and a reconnect notice.

### Renewal protocol and rotation

1. The app requests a one-time server challenge for its device UUID.
2. It generates a new random 256-bit renewal secret but keeps the current secret until success is confirmed.
3. It signs a canonical message containing the method, route, device UUID, token generation, challenge, request UUID, timestamp, SHA-256 of the current secret and SHA-256 of the next secret.
4. The server atomically verifies the unused challenge, device public key, current secret hash, generation, timestamp window, user enabled state, current role, idle lifetime and absolute lifetime.
5. The same transaction consumes the challenge, replaces the current hash with the next hash, increments the generation, updates last-used/idle expiry, revokes earlier access sessions for that device, and creates one new read/routine-command session.
6. The app commits the next secret to secure storage only after a successful response.

An exact request UUID and next-secret hash are retained as minimized rotation metadata for two minutes. An exact retry may recover from a lost response, but changed content, an old generation, a different next hash, a reused challenge or a replay outside that window is rejected and revokes the renewal family for review. Concurrent rotations permit exactly one winner.

Renewed sessions contain only `replica.read`, `commands.read` and, when separately enabled, `commands.enqueue`. They never inherit `light.control`, `camera.still`, intake submission, synchronization administration, wildcard or future capabilities.

### Device storage and revocation

- Private signing key: non-exportable Secure Enclave/hardware-backed keystore when supported.
- Renewal secret: OS Keychain/secure storage marked device-only, excluded from cloud backup and never written to preferences, logs, analytics or crash metadata.
- One-hour access token: Keychain/secure storage; never logs or URLs.
- Cached reporting DTOs: encrypted application storage with source timestamp/data-age metadata and normal OS data-protection class.

Signing out revokes the device and all of its access sessions. A server-side user disable, role change or device revoke is checked on every access and renewal. An administrator can list only minimized device metadata and revoke one device or every device for the user. Revocation never requires possession of the device secret.

## Proposed source layout

- `MobileRoutineCommandService.php`: typed DTO validation and mapping into existing `CommandService`.
- `MobileDeviceRenewalService.php`: enrollment, challenge verification, rotation, expiry and revocation.
- `MobileCapabilityPolicy.php`: explicit renewed-session capability ceiling and exact administrator-only routine policy.
- `MobileReadPolicy.php` and `public/index.php`: disabled routes and stable HTTP errors.
- `migration-009-mobile-device-renewal.*.sql`: device/challenge/rotation metadata and nullable device/session binding; declared non-automatic.
- Configuration defaults: both `mobile_routine_commands_enabled` and `mobile_device_renewal_enabled` false.

No new database principal, remote database connection, inbound HA endpoint or firewall/DNS/VPN change is required.

## Required tests before any activation

- All four command kinds accept only their exact roles and fields.
- Viewer/operator denial and cross-user command-status denial.
- Exact UUID retry deduplicates; changed-content UUID reuse fails.
- Revision conflicts remain terminal and require review.
- HA/vineyard outage leaves commands durably pending; recovery applies once.
- Lost result delivery and worker lease expiry remain idempotent.
- Renewal rotation has one winner under concurrency.
- Challenge, current-secret and generation replays fail.
- Exact lost-response retry is recoverable only inside its bounded window.
- Idle, absolute and timestamp boundary tests use UTC.
- User disable, role change, device revoke and sign-out revoke access immediately.
- Renewed sessions cannot call lights, cameras, intake, sync administration, device or power routes.
- Secrets and authorization codes are absent from access, PHP and application logs.
- Rollback with the feature flags false preserves existing one-hour HA login behavior.

## Action-time approvals required

Before migration or activation, the owner must explicitly approve:

1. the four command kinds and exact field allowlists;
2. administrator-only initial role scope (or a separately reviewed operator subset);
3. `commands.read` and `commands.enqueue` on device-renewed sessions without five-minute HA step-up;
4. the 24-hour idle and 7-day absolute renewal lifetimes;
5. the device/challenge/rotation tables and nullable device/session binding migration;
6. device enrollment, per-device/all-device revocation UI and secure-storage behavior;
7. enabling the two production feature flags after independent security review and staged outage/recovery testing.
