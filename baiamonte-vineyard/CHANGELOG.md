# Changelog

## 0.24.21

- Classify parking and parcheggio camera names as entrance views so the Main Parking camera appears on the Entrance TV page.

## 0.24.20

- Split the TV camera wall into separate Entrance and Vineyard pages while retaining the existing saved camera entity list.
- Add a simple Home Assistant option to include or hide the Vineyard camera page in the TV rotation.
- Shorten the Today-page system, power and network light labels for quick scanning on phones and small displays.
- Replace long diagnostic text with concise states such as Live, Online, Synced and Error while retaining the full detail as a tooltip.
- Expand disease and heat-stress screening to combine current and seven-day weather, leaf wetness, soil moisture, wind, solar load, phenology, scouting, maturity findings and recent treatment context.
- Show the evidence used for every pressure score and retain Sebastian's approval as the treatment decision gate.
- Add database-backed alert rules with simple severity and delivery controls for the Home Assistant app, Gmail and WhatsApp.
- Rename the Home Assistant dashboard to Vineyard Overview and add an embedded Alert Settings view to its managed dashboard definition.

## 0.24.19

- Restores the private Records-page workbook controls with a simple check-then-import workflow.
- Keeps Fatture in Cloud as the authoritative accounting source; this control imports only the vineyard, harvest and cellar workbook.

## 0.24.18

- Add a seventh TV page for cellar tanks, fermentation status, readings and next checks, using the same live database records as Vineyard Operations and clearly labeled demo data when sensors are not yet assigned.
- Add visible scales, month/year labels and measurement units to the TV vintage, temperature and rainfall charts.
- Separate Fatture and DDT into clean read-only finance views and remove funding actions from the Finance screen.
- Link every cadastral parcel record to the forMaps cadastral viewer while retaining the estate-location map and authoritative sheet/parcel identifiers.
- Remove the superseded Estate Log view from the GitHub-managed Baiamonte Overview dashboard.
- Normalize maturity, actual harvest, cellar lot, fermentation and mass-balance workbook rows during import in addition to retaining every non-empty source row for audit; an already-audited workbook can be safely reprocessed by a newer importer without duplicating its source archive.

## 0.24.17

- Do not treat Home Assistant's generic Shopping List as the shared Baiamonte task list.
- Report a configured calendar or task entity that does not exist instead of displaying it as connected.

## 0.24.16

- Add working harvest projections to the TV Today and Intelligence pages, including 15 kg crates, expected wine and bottle equivalents.
- Add a current-plan versus prior-vintage comparison and a historical average to the TV Vintage page.
- Add dedicated multi-year rainfall charts with visible year legends and monthly averages in Vineyard Operations and on the TV display.
- Reduce the oversized TV weather readings while retaining clear 32-inch visibility.
- Keep the latest disease and heat-stress assessment visible on TV with its assessment date, including during temporary weather outages.
- Expand priority work on TV and add safe explicit calendar and shared to-do entity settings with an automatic single-entity fallback.

## 0.24.15

- Publish the harvest feed with a dedicated `X-Vineyard-Token` header in addition to the standard bearer token so PHP receivers work on shared hosts that remove `Authorization`.
- Accept the dedicated header, LiteSpeed's redirected authorization variable, and `getallheaders()` as secure receiver fallbacks.

## 0.24.14

- Add a visible Processing log under Alerts & inbox for automated imports, Gmail, AI document handling, website publishing, and their error messages.
- Record successful and failed scheduled integrations without storing passwords, tokens, or full public payloads.
- Show the public website feed as disconnected, waiting, failed, or last successfully published instead of reporting a configured URL as automatically healthy.
- Diagnose the public website connection separately from the database harvest plan so recorded harvest dates remain visible while publishing is being configured.

## 0.24.13

- Apply TV camera, time-zone, rotation, refresh and network-equipment option changes directly from the saved Home Assistant configuration without requiring an add-on restart.
- Treat a configured camera list as exact so removed cameras no longer return through automatic gate/door discovery; automatic discovery remains the fallback when the list is blank.
- Mark individual camera snapshot failures clearly while continuing to refresh healthy camera tiles every ten seconds.
- Show explicit Vineyard Operations, Home Assistant calendar and shared-reminder connection indicators on the TV Work Plan page.
- Correct the Baiamonte Weather Google Sheets CSV column mapping so the authoritative 2023–2025 archive populates multi-year temperature and related weather measures.
- Add labeled color legends to the TV vintage and multi-year weather charts.

## 0.24.12

- Repair the main navigation, vintage selector, refresh control, quick-entry buttons and record buttons with an independent fallback initializer.
- Cache-bust the Vineyard Operations interface assets so Home Assistant does not retain an older broken script after an add-on update.
- Accelerate the initial Home Assistant Recorder weather backfill while retaining small, restart-safe 14-day checkpoints.

## 0.24.11

- Fix public website publishing when MariaDB returns vineyard measurements as decimal values.
- Normalize the complete public feed at its boundary so future decimal and date fields remain JSON-safe.

## 0.24.10

- Add Home Assistant network-equipment diagnostic lights for routers, gateways and access points on Today and the TV display.
- Auto-discover clearly named network entities and allow an authoritative comma-separated entity list in `network_equipment_entities`.

## 0.24.9

- Add a live Today-page countdown to the next planned or forecast harvest date.
- Show currently playing media from the Baiamonte Home Assistant speaker group on Today.
- Align multi-year weather and laboratory series on a shared seasonal axis with clearer overlays and year legends.
- Improve the main multi-year chart with a continuous year trend and clearer missing-data gaps.
- Add simpler, explicit enologist approval controls to laboratory decisions.
- Add a Projects & Priorities workspace with internal vineyard work, Home Assistant Google Tasks, and Google Calendar views, plus a rotating TV work-plan page.
- Add Cellar Operations with clearly marked old-system demo tanks, fermentation processes, and a path to the future tank-monitor entities.
- Put live weather at the top of Today, expand weather measures to solar and evapotranspiration, and add clickable parcel detail views with map links.
- Add read/print actions for Fatture and DDT documents and default Finance to open documents, with optional all or closed/paid filters.
- Add simple vintage blend planning with component quantities, target grapes, estimated 15 kg crates, expected wine yield, target volume and bottles, timing, approval, and prior-vintage comparisons directly inside Grapes & Vintage.
- Make the TV page cycle and data-refresh intervals configurable in the add-on options (25 seconds and 120 seconds by default).
- Drive Projections from the current blend plan when one exists, including estimated 15 kg crates, liters, and bottle equivalents.
- Recalculate the displayed harvest recommendation from recorded weather/GDD forecasts, grape labs, maturity samples, field reports, and the manual plan, while retaining human approval.
- Separate background ingestion timers so weather and Gmail no longer interfere, keep uploads/WhatsApp analysis immediate, and optionally refresh the read-only Fatture in Cloud mirror every 360 minutes.
- Make configured TV camera entities authoritative and use automatic gate/door discovery only to fill remaining camera slots.

## 0.24.8

- Show the live Solar, Grid, Generator, and Battery lights on the main Vineyard Operations Today page as well as the TV kiosk.

## 0.24.7

- Add live Solar, Grid, Generator, and Battery indicator lights to the TV Today page using available Home Assistant power sensors.
- Treat nighttime/zero production as idle rather than an error, and label missing sensors without inventing a status.

## 0.24.6

- Show a red GW2000 service indicator when Home Assistant reports no usable live weather entities instead of marking an empty sync as healthy.

## 0.24.5

- Fall back to strongly named Home Assistant weather sensors when the GW2000/Ecowitt device prefix is absent from generated entity IDs.

## 0.24.4

- Prefer the current Home Assistant GW2000 observation on the TV Today page while retaining MariaDB observations as the historical series.

## 0.24.3

- Discover GW2000/Ecowitt weather sensors from their entity IDs, friendly names, and device classes so renamed Home Assistant entities still populate the Today and TV weather views.
- Use the same discovered entity set for live readings and Recorder history imports.

## 0.24.2

- Make Home Assistant camera, solar, weather, and notification access resilient to both current and legacy Supervisor token injection paths.
- Keep all Home Assistant credentials private; diagnostics continue to report presence only, never token values.
- Show the TV clock, date, greeting, and update time in the configurable vineyard time zone (Europe/Rome by default).

## 0.24.1

- Requests the Home Assistant supervisor token needed for live camera, solar and GW2000 access.
- Ignores placeholder `null` treatment text and prevents stale historical plans from replacing the current disease-pressure review.

## 0.24.0

- Simplifies Treatments around one clear next action, timing, and evidence-based reason.
- Adds yearly treatment totals, monthly history, current disease pressure, and a processed-actions audit view.
- Adds Today and TV service indicator lights plus a fuller TV Today page.
- Adds DDT mirroring, Fatture in Cloud sync indicators, printable reporting copies, year-over-year finance charts, and projections.
- Adds Gmail check controls for the reviewed intake workflow.
- Adds detailed grape harvest lots and cellar blend/yield details to the Vintage page.
- Includes a secure public website feed receiver and an updated `about.php` using the sanitized vineyard database feed.

## 0.23.1

- Add safe Home Assistant connection diagnostics to the LAN-only TV data feed so missing solar, weather, and camera access can be resolved without exposing the Supervisor token.

## 0.23.0

- Add a fifth automatically rotating TV page with the live Home Assistant ADS-B aircraft map on port 8080.
- Use the Home Assistant host address so the map works from the vineyard TV and other kiosk browsers.
- Keep the aircraft map interactive, with a pause-rotation hint and a full-map control in the Baiamonte display design.
- Automatically include Home Assistant gate, door, entrance, driveway, and access cameras on the TV camera wall while excluding unrelated indoor cameras.

## 0.22.2

- Accept workbook vintage years stored as decimal text when backfilling authoritative treatments under MariaDB strict mode.

## 0.22.1

- Fix the MariaDB treatment migration so the application starts cleanly after the 0.22 update.

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
