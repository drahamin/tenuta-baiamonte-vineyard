# Changelog

## 0.22.0

- Make the Vineyard Operations menu a responsive two-row layout and improve readable charts throughout the app.
- Restore authoritative historical vintage totals in multi-year harvest and cellar comparisons, without turning missing values into zeroes.
- Import and display the five authoritative vineyard treatment instructions with source text, assignments, doses, and clear missing-actual warnings.
- Add focused English/Italian AI questions for laboratory results and treatments, while keeping treatment approval with the agronomist.
- Add an interactive AI review inbox for documents, photos, screenshots, Gmail, and WhatsApp items before proposed data is saved.
- Keep original intake files attached to the approved lab, treatment, harvest, labor, observation, issue, or decision record.
- Add laboratory reading guidance, prior-result comparison, editable review notes, and full multi-year trends.
- Add practical issue and decision controls for monitoring, recording a decision, and resolving an item.
- Add selectable multi-year comparisons for vintages, projections, and olives, including actual results against working projections.
- Improve Home Assistant weather, solar, and camera discovery for the TV display and add restrained motion with reduced-motion support.
- Show visible source errors instead of leaving optional panels silently blank.

## 0.21.0

- Replace workbook-style data entry with six simple daily actions: work, harvest, cellar, treatment, labor, and observation.
- Keep maturity samples, new cellar lots, fermentation checks, equipment/sanitation, labs, stock, olives, and issues under one optional section.
- Add gross/tare harvest reconciliation and optional lot, condition, destination, fruit-temperature, and Babo fields.
- Add a multi-year operating view for harvest, cellar, labor, treatments, laboratory samples, olives, and oil.
- Fix photo and PDF attachments on quick-entry records so evidence links to the saved row.
- Add live Home Assistant solar information and core vineyard facts to the TV display.
- Add a fourth TV page with six explicitly selected exterior Home Assistant camera views; the supervisor token stays server-side.
- Rotate all four TV pages automatically every 25 seconds, with manual navigation, pause, and fullscreen.
- Add English/Italian assistant voice dictation and answer playback without storing recordings.

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
- Add a dynamic, presentation-safe Baiamonte TV webpage on LAN port 8101 with live rotation, charts, full-screen controls, and no write routes.
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
