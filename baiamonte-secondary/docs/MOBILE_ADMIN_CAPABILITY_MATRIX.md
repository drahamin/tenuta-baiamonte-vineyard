# Mobile administrator capability matrix

This is a staged product contract, not an activation. David's existing role is
resolved from `app_users` as `admin`. The app never supplies or promotes a role.
An administrator can eventually use every explicitly authorized Baiamonte
function, but no token receives a wildcard and no role bypasses domain safety.

## Capability evaluation

Every request must pass all three checks:

1. the enabled server-side user role permits the capability;
2. the current token contains that exact capability;
3. the route-specific validation succeeds, including step-up where required.

The first approved connection issues only `replica.read` for one hour. Therefore
an admin identity is displayed correctly while all writes remain unavailable.
Additional capabilities require a later reviewed release and explicit activation.

| Capability | Viewer | Operator | Admin | Route family | Extra controls |
| --- | --- | --- | --- | --- | --- |
| `replica.read` | yes | yes | yes | `GET me/status/catalog/records` | role-specific mobile object/field allowlists and exact estate row boundary |
| `commands.read` | no | yes | yes | `GET mobile/v1/commands` | actor-scoped history |
| `commands.enqueue` | no | yes | yes | `POST mobile/v1/commands` | fresh HA step-up; user confirmation; UUID, expected revision, domain validation and audit |
| `camera.still` | no | no | yes | `GET/POST mobile/v1/camera-snapshots` | fresh HA step-up; allowlisted still only; manual request; audit |
| `admin.sync.read` | no | no | yes | `GET mobile/v1/admin/sync-config` | status metadata only; never return secrets |
| `admin.sync.rotate` | no | no | yes | `POST mobile/v1/admin/sync-config` | fresh HA step-up; owner confirmation; secret redaction; audit |

`replica.read` catalog output is only configured reporting-object names. It does
not return command types, credentials, key identifiers, camera identifiers,
private configuration, schema details or excluded source objects.

## Step-up contract

Sensitive actions start a new user-initiated HA login. The resulting grant is
bound to the current mobile session, exact capability, exact client, HA OAuth
state and PKCE verifier. It expires in at most five minutes and is consumed for
the confirmed action. Re-authentication does not expose or retain an HA token.

The server re-reads the enabled user and role immediately before execution.
Changing a role or disabling the account invalidates authorization. All attempts,
including validation failures, receive redacted audit records.

## Non-bypassable controls

Admin does not bypass object/field allowlists, expected revisions, command UUID
deduplication, conflict review, atomic inventory-transfer validation, camera
allowlists, data-age reporting, CSRF/browser separation or audit logging.

No mobile capability exists for raw SQL, arbitrary source-table access, payroll,
financial data, security credentials, live camera streams, audio, device control,
service control, network changes, generator, inverter, relay, load or power
control. Adding any such capability requires a separate threat model, approval,
migration and release; it cannot be inferred from the `admin` role.
