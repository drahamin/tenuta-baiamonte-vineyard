# Backend modularization

The backend remains one FastAPI application and one authoritative MariaDB
database. Modularization is a behavior-preserving extraction, not a service
rewrite.

## Invariants

- Existing paths, HTTP methods, authorization dependencies, status codes, and
  response fields remain compatible during extraction.
- Domain modules never import `app.main`.
- Routes authorize and validate; services assemble domain behavior and own
  database transactions.
- Query optimization and user-visible changes occur after a boundary has been
  extracted and verified, not in the same change.
- Every step must pass the complete test suite and the live integrity audit
  before release.

## Extraction sequence

1. **Admin Control foundation** - process health, runtime, connections,
   recovery errors, storage, and setup warnings. This boundary is now located
   in `app/domains/admin_control.py`; `/api/v1/admin/control` remains compatible,
   and `/api/v1/admin/control/runtime` provides an independently loadable slice.
2. **Admin people and presence** - Home Assistant people, trackers, presence,
   per-person IVR profiles, and directory assembly.
3. **Admin labor and payment review** - reconciliation, timesheets, worker
   submissions, payment holds, and integrity checks.
4. **Communications (complete)** - Gmail routes are isolated in
   `app/domains/communications_gmail_routes.py`. The linked system WhatsApp
   control plane and authenticated intake are isolated in
   `app/domains/communications_system_whatsapp_routes.py`, backed by
   `app/domains/system_whatsapp_control.py`. Official Meta WhatsApp state is in
   `app/domains/communications_meta.py`; its aggregate, outbound and
   administration routes are in `app/domains/communications_meta_routes.py`;
   the signed webhook is in `app/domains/communications_meta_webhook_routes.py`;
   and stateful personalized conversation behavior is in
   `app/domains/communications_whatsapp_assistant.py`. The composition root no
   longer owns communications route or conversation logic.
5. **Worker portal and payroll administration (complete)** - worker-owned
   entry routes live in `app/domains/worker_portal_routes.py`; administrative
   review, correction, presence and payment routes live in
   `app/domains/payroll_admin_routes.py`, with presence and payroll summaries
   supplied by focused services.
6. **Cellar and tank operations (complete)** - cellar dashboard, tank lifecycle,
   manual readings, maintenance, traceability, legal labels and tablet
   enrollment live in `app/domains/cellar_routes.py`.
7. **Dashboard and historical aggregation (complete)** - the operational and
   grape dashboards plus multi-year overview live in
   `app/domains/dashboard_routes.py`.
8. **Alerts, intake and attachments (complete)** - alert preferences and state,
   attachment storage, intake review, processing history and manual Gmail
   refresh live in `app/domains/alerts_intake_routes.py`.
9. **Public feeds and static pages (complete)** - token-gated harvest feeds,
   weather-map proxying and browser entry pages live in
   `app/domains/public_routes.py`.
10. **Intelligence control and assistant boundary (complete)** - provider,
   cost and request-profile administration, durable learning rebuilds,
   assistant questions and review-gated suggestion intake live in
   `app/domains/intelligence_routes.py`.
11. **Remaining intelligence services** - separate disease prediction, intake
   analysis, power continuity, sensor processing and external integrations one
   tested service boundary at a time.

## Service separation status

Route ownership and service ownership are tracked separately. The route
boundaries above are complete, while transaction-heavy service extraction is
incremental. Shared attachment persistence now owns sanitizing, hashing,
filesystem writes and rollback cleanup. Payroll presence is transport-neutral,
and worker review calculation and locking are owned by the payroll service.
Remaining cellar, intake and administrative handlers should move one tested
transaction at a time rather than combining a second behavior change with the
route extraction.

## Definition of done for each boundary

- The original aggregate endpoint still works.
- A focused router or service owns the extracted behavior.
- Contract tests cover route protection and response semantics.
- Runtime contract tests inspect the registered FastAPI routes rather than only
  searching concatenated source text.
- `main.py` contains less domain logic than before the extraction.
- The full automated suite, import/compile check, and live year-switch and
  integrity audit pass.
