# Changelog

## 0.20.0

- Add transparent Baiamonte app/sidebar logos for both light and dark themes.
- Fix Vintage, Refresh, quick-entry cancellation, and all Vineyard Records controls.
- Add treatment history and safety status, weather-based disease/heat pressure screening, agronomist review tracking, and alerts.
- Add historical laboratory reports, multi-year charts, searchable results, and audited corrections.
- Add multi-year weather comparisons, Baiamonte Weather CSV import, and incremental Home Assistant GW2000 recorder backfill/live sync.
- Add a review inbox for Gmail attachments, WhatsApp webhook messages, photos, screenshots, and uploaded reports.
- Add optional OpenAI-powered extraction and read-only vineyard questions; treatment approval remains human-controlled.
- Make Finance a read-only reporting mirror of authoritative Fatture in Cloud records.
- Add the tested Baiamonte Overview dashboard and REST sensor package to the GitHub release.
- Add workbook-style Grapes & Vintage, Projections, Olives, Blocks & Atlas, Issues & Decisions, full Lab Trends, and Weather Trends pages.
- Add optional photo/PDF evidence to field observations, labor, work, harvest, cellar, treatments, lab samples, olives, and issues.
- Automatically analyze approved Gmail, WhatsApp, photo, screenshot, and document intake into structured review records.
- Add a separate Finance-free kiosk dashboard for the `display` NSPanel and `tv` accounts.
- Rename the Home Assistant sidebar item to Vineyard Operations.

## 0.1.5

- Allow finance-only, funding-only, or vineyard-only workbook imports.
- Ignore the empty upload placeholders browsers send for unselected workbook fields.

## 0.1.4

- Resolve finance products by either their existing name or SKU during workbook imports.
- Backfill a missing SKU when the workbook matches an existing product by name.
- Let every quick-entry dialog close with Cancel, the close button, Escape, or a backdrop tap without requiring input.

## 0.1.3

- Fix MariaDB workbook imports when a season or grape variety already exists.
- Keep the import transactional and preserve the existing database identifiers.

## 0.1.2

- Add the official Tenuta Baiamonte logo and app icon to Home Assistant.
- Add a finance-only workbook check and controlled import screen.
- Require explicit backup verification before any workbook rows are committed.
- Keep each import transactional, size-limited, and traceable to source rows.

## 0.1.1

- Allow the optional external website publishing URL to remain blank.
- Include the MariaDB schema, vineyard interface, finance access controls,
  contractor hours, laboratory comparisons, reporting, and public harvest feeds.
