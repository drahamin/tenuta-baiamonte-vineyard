# System audit — release 1.7.0

Audit date: 2026-08-29  
Scope: live Home Assistant add-on, application and integration runtimes, MariaDB integrity, API latency and payloads, browser resources, release pipeline, dependencies, tests and operator documentation.

## Live baseline

- Database connectivity passed and the integrity audit reported no blocking data-quality issue.
- Payment reconciliation reported zero orphan payments, overpayments, paid-status mismatches or balance mismatches.
- Processing runtime reported no active or timed-out jobs and no processing error in the preceding 24 hours.
- Scheduled processes were healthy and retained their persisted cadence across restarts; the full refresh is a recovery sweep rather than a simultaneous startup burst.
- Storage was 23.3% used with approximately 183 GB free.
- The running add-on used approximately 313 MB and 0.39% CPU during the audit.
- Nine laboratory records remained in their explicit human-review queue. They are review work, not integrity failures.

## Performance evidence

The prior default startup requested 26 API resources together and transferred approximately 1.9 MB of JSON before the first complete render. Large hidden workspaces included Agronomy (about 401 KB and 2.5 seconds in the live sample), Cellar (about 246 KB), Grapes (about 220 KB) and Projections (about 199 KB). The local JavaScript, CSS and HTML source set was approximately 1.3 MB before compression.

GZip was already working correctly: representative reductions were approximately 210 KB to 42 KB for the main stylesheet and 300 KB to 82 KB for the main JavaScript. The remaining asset problem was cache policy: release-versioned URLs still required revalidation on every visit.

## Release 1.7.0 changes

- The default Today route now renders from dashboard, tasks, current weather and alerts, then hydrates the complete hidden workspace data set in the background.
- Non-Today deep links and explicit full refreshes retain the complete atomic loader.
- Release-versioned JavaScript and CSS are cached for one year as immutable; unversioned development URLs still revalidate.
- Leaflet CSS and JavaScript no longer block every page. They load on first Atlas use with a second CDN and satellite iframe fallback.
- Public publisher checkpoints now use MariaDB local time consistently with health calculations and integration-event timestamps.
- The owner manual, changelog and application release identity were updated to 1.7.0.

## Release gate

The local release gate passed 820 tests and 15 subtests. Python compilation, every JavaScript syntax check, `pip check`, the production Node audit and repository whitespace checks passed; the Node audit reported zero vulnerabilities. The rebuilt 48-page A4 manual was rendered in full and visually checked for clipping, overlap, broken transitions, headers and page numbering.

GitHub repeated the clean install, dependency checks, production Node audit, compilation, JavaScript validation and full test suite successfully. The workflow itself was then moved to current Node 24-compatible `v7` checkout, Python and Node setup actions and passed again without the prior deprecation annotation.

Home Assistant Store refresh detected version 1.7.0 as available while the validated 1.6.98 installation remained running. After installation, repeat the live integrity audit and confirm the published-feed indicator is no longer falsely overdue.
