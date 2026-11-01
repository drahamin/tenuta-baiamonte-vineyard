# Mobile reference: existing TV Today

Status: source reference only. This document adds no route, credential, replica object, capability, or production change.

## Canonical implementation

- Kiosk route: `GET /tv` on the Vineyard Operations display service (`app/display_server.py`). The port root and `/display` are aliases of the same renderer.
- Read model: `GET /api/display-data`, backed by `display_payload()` in `app/display_data.py`. The server shares one payload for 90 seconds; configured clients normally refresh every 120 seconds.
- Today markup: screen `data-screen="0"` in `app/static/display.html`.
- Today renderer: `render(d)` in `app/static/display.js`, especially the Today block beginning with `const dash=d.dashboard`.
- Layout and responsive behavior: `app/static/display.css` plus `app/static/display-extra.css`.
- Source tests: `tests/test_tv_display_compatibility.py`, `tests/test_weather_animation.py`, `tests/test_unified_work_plan.py`, and `tests/test_earthquake_alerts.py`.

## Today visual hierarchy

The mobile app should borrow the information hierarchy, not copy the television density:

1. Estate greeting and source-updated state.
2. Service/network/power status rail. Mobile may show only approved read-only state; it must not infer or expose controls.
3. Urgent findings rail for active/recent Etna, earthquake, or operational alerts.
4. Six headline metrics: solar now or estimated solar, fruit received, working wine outlook, vineyard stage/harvest calendar, open work, and cistern state.
5. Current weather card with temperature, humidity, rain, wind, observation time, derived details, and a three-period forecast.
6. Vineyard-year card with the current stage, next stage, focus items, and estate facts.
7. Next-work card composed from canonical open work plus privacy-minimized hospitality schedule.
8. Next-decision card for treatment screening, explicitly labelled as decision support requiring agronomist review.

On a phone, render this as a single vertical sequence. On a tablet/desktop, use a two-column grid after the headline metrics. Preserve the existing dark estate palette, restrained gold accents, serif display headings, status pills, explicit empty states, and `—` for unknown measurements.

## Minimum sanitized Today DTO

The full LAN TV payload is broader than the approved mobile replica and is not itself a mobile API contract. A mobile Today composer should use only fields already supplied by approved mobile endpoints or permitted replica objects:

- `source`: `source_generated_at`, `last_success_at`, `data_age_seconds`, `state`.
- `weather`: observation timestamp and allowlisted measured weather values; missing measurements remain null/absent.
- `weather_forecast`: bounded periods with date/time, condition, high/low temperature, precipitation probability/amount, and wind speed.
- `estate_stage`: stage name, summary, next stage, basis, last harvest date, harvested quantity, and bounded focus items.
- `headline`: read-only solar/energy availability, fruit received, working wine outlook, open-work count, and cistern availability when each source is separately approved.
- `work`: bounded, estate-scoped open items with ID, lossless revision string, title, status, priority, due date, category, and block reference. Exclude assignee contacts, notes, costs, payroll, and arbitrary nested data.
- `hospitality`: only the existing privacy-minimized schedule view. Exclude names, contact details, notes, payments, prices, and confirmation codes.
- `decision_support`: minimized treatment-screening headline, timing, reason, confidence and review state. Never present it as an approved treatment command.
- `alerts`: minimized active status, severity, title, timestamp and stable category. Exclude raw payloads and private owner/contact fields.

Do not expose the TV payload's cameras, traffic feeds, communications content, private network details, power/device controls, raw Home Assistant entities, or broad system diagnostics through mobile. Mobile remains backed by its existing authenticated, estate-scoped endpoints and must show source age and unavailability explicitly.
