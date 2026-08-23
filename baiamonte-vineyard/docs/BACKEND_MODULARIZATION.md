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
5. **Remaining composition-root handlers** - worker portal, cellar/tanks,
   dashboard/history, alerts/attachments, and public feeds.
6. **Intelligence services** - extract disease, intake analysis, power
   continuity, sensor processing, and external integrations only after their
   route boundaries are stable.

## Definition of done for each boundary

- The original aggregate endpoint still works.
- A focused router or service owns the extracted behavior.
- Contract tests cover route protection and response semantics.
- `main.py` contains less domain logic than before the extraction.
- The full automated suite, import/compile check, and live year-switch and
  integrity audit pass.
