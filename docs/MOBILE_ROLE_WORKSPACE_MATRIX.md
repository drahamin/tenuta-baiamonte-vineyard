# Mobile role workspace matrix

Status: disabled design contract for security review. It creates no account, role, entitlement, route, capability, migration, or production flag.

## Authorization model

The existing authenticated roles remain `viewer`, `operator`, and `admin`. They are the outer authorization ceiling. The proposed mobile workspaces are a second, server-stored restriction inside that ceiling:

- `owner_admin`
- `enology`
- `agronomy`
- `field`

An account receives only workspaces explicitly provisioned on the server. The client may select among those returned by the authenticated `/me` response, but selection is display filtering only. It cannot add a workspace, dataset, action, capability, role, or estate. Every request is independently checked against the authenticated session role, token capability, server workspace entitlement, exact dataset/action policy, and estate boundary.

The actor always comes from the authenticated session. Requests containing a user, role, person, estate, entitlement, or capability override must be rejected or ignored before domain validation. Multi-role accounts receive the union of their server-stored workspace entitlements, never the union of every workspace their base role could theoretically use.

The approved owner/administrator account may receive `owner_admin`. No literal production username belongs in the public source contract.

## Proposed projection matrix

| Workspace | Minimum existing role | Read projection | Submit/action projection | Explicit exclusions |
| --- | --- | --- | --- | --- |
| Owner / administrator | `admin` plus `owner_admin` entitlement | All currently authorized mobile replica, Work, Review, intake status, freshness, minimized directory, weather, calendar, enology, energy and Etna views | Existing authorized intake; approved still cameras, sync administration and approved light controls only when their separate capability and fresh-auth checks pass; own timeclock when separately activated | Power, generators, inverters, load control, arbitrary devices, raw SQL, finance and payroll; no staff time correction without a separately reviewed supervisor command |
| Enologist | `operator` or `admin` plus `enology` entitlement | Wine lots, cellar containers, vintages, fermentation observations and authorized enology history; lab queue/history only after a separate review entitlement is approved | Existing typed enology/intake reports; proposed cellar operation submission only after the distinct `cellar.operations.submit` capability and authoritative handler are approved | Field treatment commands, agronomy approval, lights, cameras, sync administration, payroll and device control |
| Agronomist | `operator` or `admin` plus `agronomy` entitlement | Assigned/open work, issues, weather, calendar, vineyard/harvest/treatment reporting context and permitted block/season references | Existing field, damage and agronomy intake reports; treatment remains decision support until a separately approved authoritative action exists | Cellar operations, lab approval, enology administration, lights, cameras, payroll and device control |
| Field worker | `operator` or a future narrower base role plus `field` entitlement | Minimized assigned/open work, weather, permitted block/season context and own submission status | Existing work/field/damage intake reports; own timeclock events only after activation | Whole-estate directory, private owner details, enology, lab review, cellar commands, lights, cameras, sync administration, payroll approval and other-person timeclock actions |

The current `operator` role exposes the same replica catalog and Work datasets to every operator. Therefore the three operational workspaces must not be activated by mapping them directly to `operator`. Activation requires server-side dataset/action entitlements, or a reviewed narrower role/profile mapping, enforced below every endpoint before records are fetched.

## Exact request decision

For every mobile request, the server must evaluate all of the following and deny when any check fails:

1. The access token is valid, unexpired, unrevoked and bound to an enabled account.
2. The account's existing base role permits the route's outer capability.
3. The token contains that capability; an account role never enlarges the token.
4. The requested workspace is in the account's server-stored entitlement set.
5. The exact dataset or domain action is allowlisted for that workspace.
6. The authenticated estate equals the configured estate boundary.
7. The actor/person is taken from the session; a submitted actor cannot replace it.
8. A sensitive action has the required recent step-up and expected entity revisions.

Workspace selection does not change the session. A request may include an allowlisted workspace identifier only to select the narrower projection; the server derives the effective workspace from the intersection above.

## Cache and account isolation

All device caches must be partitioned by `user_id + estate_id + workspace + server_policy_version`. Query caches, offline queues, attachment metadata and optimistic UI state must use the same partition. Sign-out, revocation, account change, estate change, workspace removal or policy-version change purges the affected partitions and encryption keys. No account may read another account's cached response, even when both accounts share a device or base role.

Offline submissions retain the session-derived actor and workspace entitlement snapshot for audit, but reconnect processing re-evaluates the current account, role, entitlement, capability and estate before acceptance. Removed access leaves the item rejected or quarantined for review; it is never silently submitted under another signed-in account.

## Activation gate and verification

Before any workspace is enabled, approve the exact account-to-workspace assignments, per-workspace dataset fields, action capabilities, step-up ages and migration. Verification must include:

- A complete role/workspace/endpoint matrix test in which every non-allowlisted pair receives 403 without leaking whether a record exists.
- Cross-account, cross-workspace and cross-estate cache tests on one device.
- Offline sign-out, account-switch, entitlement-removal and recovery tests.
- Server-side actor-forgery tests for user, role, person, estate and capability fields.
- A test proving that UI workspace switching cannot change the `/me` entitlement set or token capabilities.
- Existing conflict, idempotency, revision and authoritative domain validation tests for every write action.

Until those gates pass, this matrix remains documentation only and the existing production role behavior is unchanged.
