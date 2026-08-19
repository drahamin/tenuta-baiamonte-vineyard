# Tenuta Baiamonte System Audit - 19 August 2026

## Scope

- Live Vineyard Operations version and process health.
- MariaDB and payment integrity.
- Baiamonte MCP configuration, authentication, tool discovery, and live read call.
- Local Codex MCP configuration posture.
- GitHub repository, open pull requests, review threads, and notification emails.

## Live result

- Version 1.3.25 was installed and current when the audit began; repairs are packaged in 1.3.26.
- Add-on state: started.
- Database: connected.
- Processing errors in the last 24 hours: 0.
- Unhealthy processes: 0.
- Failed intake items: 0.
- Recovery errors: 0.
- Payment-ledger mismatches: 0.
- Fully paid invoices reappearing: 0.

## MCP result

- Baiamonte MCP client is enabled at the local/VPN endpoint.
- Bearer token is supplied through `BAIAMONTE_MCP_TOKEN`.
- Authenticated MCP initialize request returned HTTP 200.
- Unauthenticated MCP request returned HTTP 401.
- Twenty-three tools were discovered.
- Live `processing_status` call completed successfully.
- MCP writes are enabled and require exact-record confirmation.
- The MCP framework reports version 1.29.0 while the repaired application release is 1.3.26; update checks must use the Home Assistant add-on version.

### Security finding

A separate `local_mcp` client stores a credential directly in its URL. Rotate that credential and move it to a protected environment or connector secret. The credential value is intentionally omitted here.

## GitHub notification result

The messages from `notifications@github.com` are automated Codex pull-request reviews, not random code sent to the server. They are triggered when a PR is opened or marked ready.

- Vineyard review emails inspected: 7.
- Automated suggestions inspected: 10.
- Resolved in later main: 1.
- Valid but not active on the sole live installation: 1.
- Still applicable to current main: 8.
- Open GitHub issues: 0.
- Open pull requests: 2 (#67 and #120), both apparently superseded and requiring closure rather than merge.

## Repaired review findings (1.3.26)

1. Migration 059 updates olive source IDs without an estate predicate.
2. Unsaved olive years can look like a valid EUR 0 cost model.
3. Fresh installs may lack the authoritative 2024 olive record.
4. Prepared Gmail replies can remain hidden inside collapsed Communications.
5. Atlas can retain stale geometry after a hidden refresh.
6. Stale intake work may fail to reclaim because the claim update is a no-op.
7. Unapproved WhatsApp senders can receive a download-error reply.
8. Compact WhatsApp contacts can ignore the `hidden` filter because of `display:block!important`.

All eight findings were repaired in release 1.3.26 and covered by focused regression tests plus the complete application test suite.

## Existing data-review queue

- 9 laboratory reports needing review.
- 5 treatment safety-detail gaps.
- 1 future-dated labor/reimbursement record.
- 1 shared planned container; 0 shared occupied containers.

These items are already visibly flagged and are not counted as live processing failures.
