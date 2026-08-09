# Changelog

## 0.24.49

- Generate Vineyard Operations and TV asset cache keys directly from the installed add-on version so future updates always load matching JavaScript and styles.
- Restore responsive navigation, page selectors, refresh controls, processing-log access and other interactive controls that could remain stuck on cached 0.24.35 assets.
- Serialize cistern observation timestamps safely when publishing the camera estimate to Home Assistant, clearing the cistern and full-refresh processing failures on the next cycle.

## 0.24.48

- Turns on the cistern camera light briefly before each scheduled level image, then restores its previous state immediately after capture.
- Supports an explicit Home Assistant light or switch entity and automatically discovers a matching camera light when the setting is blank.
- Records whether illumination was used alongside the estimate audit metadata.
- Shows each disease and stress assessment as current-dated data with a rolling 14-day progression and rising, stable, or falling direction in Vineyard Operations and on the TV.

## 0.24.47

- Estimates the cistern water level from one private camera still during each configured full-system refresh.
- Stores only the percentage, confidence, and audit metadata in MariaDB; the camera image is not retained.
- Publishes the estimate and low-water state across Vineyard Operations, the TV display, Vineyard Overview, the NSPanel display, and the admin dashboard.
- Retains the last valid estimate when the camera or AI is unavailable and rejects low-confidence or unconfirmed large changes.

## 0.24.46

- Uses the dedicated Generic Camera RTSP entity for every internal-cistern camera view.
- Removes obsolete Eufy P2P start, stop, snapshot and connection controls from the RTSP-backed camera page.
- Keeps the RTSP username and password stored privately in Home Assistant rather than in the GitHub-managed dashboard.

## 0.24.45

- Replaces the misleading grey cistern previews with compact connection-status tiles.
- Adds a dedicated WebRTC viewer for the connected internal cistern camera with Start, Stop, Refresh, and Back controls.
- Keeps the Cistern 360 tile linked to its existing PTZ WebRTC viewer.

## 0.24.44

- Adds one-tap Eufy P2P stream controls for the internal and 360 cistern cameras, plus a snapshot refresh control.
- Uses the live camera view after the stream is started so the Water page shows video instead of a grey event-image placeholder.

## 0.24.43

- Reorganizes Vineyard Overview into eight clearly named top-level sections and adds a compact Systems hub with access to every detailed system, device, and entity page.
- Replaces missing vineyard counter entities with direct, reliable Vineyard Operations controls on Home and Alert Settings.
- Removes the self-embedded alert-settings frame that remained stuck on Loading and replaces it with compact navigation controls.
- Restores both cistern cameras using Eufy event images as reliable previews, with direct access to the internal camera and the Cistern 360 PTZ page.
- Simplifies the weather forecast comparison and compacts the fire-safety layout without removing detector details or history.

## 0.24.42

- Repairs the Home Assistant update dialog by removing a duplicated old top-level version heading from the end of the changelog.
- Adds the missing 0.24.40 and 0.24.41 release notes so Home Assistant identifies the latest update correctly.
- Includes the GitHub-managed dashboard registration fixes from 0.24.40 and 0.24.41.

## 0.24.41

- Keeps the full Home Assistant Core configuration check when an API token is available.
- Uses strict dashboard marker, file-presence, and idempotence checks when this installation does not expose its Supervisor token to the app.
- Retains timestamped configuration backups and restores them on any real validation failure.

## 0.24.40

- Uses Home Assistant Core's documented configuration-check API and accepts its `valid` response.
- Flushes dashboard-manager validation details into the app log for clear troubleshooting.

## 0.24.39

- Fixes the packaged entrypoint import path so the dashboard manager loads correctly from the add-on image work directory.
- Keeps the 0.24.38 configuration-backup, validation, and rollback protections unchanged.

## 0.24.38

- Makes Vineyard Overview, Display Panel, and Admin authoritative GitHub-managed YAML dashboards.
- Adds a one-column, touch-friendly Display Panel for vineyard-building NSPanels.
- Adds an admin-only dashboard for application updates, processing health, networking, power distribution, solar commissioning, security, and camera diagnostics.
- Safely installs dashboard files into Home Assistant with a timestamped `configuration.yaml` backup.
- Validates the Home Assistant configuration through Supervisor and automatically restores the backup if validation fails.
- Preserves existing Lovelace settings and unrelated dashboards; future releases update only the marked Baiamonte dashboard block.

## 0.24.37

- Add a compact Controls & Power view to Vineyard Overview with live estate load, current, voltage, daily use, circuit loads, service outlets and the working light controls.
- Require a deliberate hold before changing the estate main breaker and remove retired Bluetti information from the operational solar view.
- Prepare the solar and energy views for the installed Growatt SPF 5000 ES and two Felicity LPBA48100-OL batteries (10.24 kWh nominal), using USB Growatt telemetry and a USB CAN adapter for BMS data when Home Assistant creates the live entities.
- Improve the Home solar summary so useful estate consumption and Solcast data remain visible while the new inverter and battery telemetry is being commissioned.

## 0.24.36

- Normalize saved ADS-B dashboard URLs before the Vineyard Operations weather-map proxy uses them, matching the working TV proxy and restoring the precipitation overlay and readiness check on the regular Weather page.

## 0.24.35

- Publish the ten nearest ADS-B aircraft and AIS vessels into Home Assistant every minute so Vineyard Overview uses the working local receiver services instead of stale helper sensors.
- Add configurable Home Assistant level, temperature, density, Brix and pH entity mappings for real cellar tanks in Live mode.
- Add separate Alert Settings controls for cellar temperature, tank level, density/pH, monitor availability and overdue cellar checks, with all editable thresholds kept in the normal GUI instead of add-on configuration.
- Remove the TV cellar demo banner while retaining the explicit Demo/Live configuration selector.
- Keep TV weather advisories in normal page flow, shorten their footprint and prevent them from overlapping the weather heading or precipitation map.
- Remove the redundant explanatory card below the Vineyard Overview aircraft and vessel lists.

## 0.24.34

- Keep Vineyard Operations navigation in two intentional rows: daily operations, then intelligence and records.
- Make the embedded precipitation map fill its panel and suppress aircraft markers and labels.
- Show configured fermenter, aging tank, barrel, amphora, demijohn/damigiana, press and general tank shapes with animated liquid levels on the Cellar and TV pages.
- Always show the displayed cellar volume in liters, including while the configurable Demo mode is selected.
- Show a prominent AIRSPACE CLOSED banner on the ADS-B TV page only when a recent official Catania Airport notice explicitly reports a closure; distinguish restrictions and ash advisories without claiming closure.
- Screen GW2000 readings and Home Assistant forecasts for thunderstorms, lightning, hail, extreme heat, frost/freezing, damaging wind, heavy rain/runoff, snow/ice, low visibility, high fire-weather risk, very high UV and dry-soil heat stress, with concise vineyard actions on the Weather page, TV and configured alert channels.
- Refresh dashboard asset cache keys so Home Assistant loads the corrected layout immediately.

## 0.24.33

- Remove semicolons embedded inside projection and authority seed values so the Home Assistant migration runner executes migrations 016 and 017 atomically.

## 0.24.32

- Add a configurable home airport to the ADS-B TV page, defaulting to Catania Fontanarossa (LICC / CTA).
- Add official METAR/TAF weather, Catania Airport disruption notices and Etna ash-impact decision support.
- Show a themed home-airport marker on the TV airspace map with clear aviation guardrails.
- Fit Projects, priorities and calendar into one TV-safe row with database work and Google connection status visible.
- Move the workbook's grape allocations, finished-wine outputs and 2026–2031 production outlook into editable MariaDB tables.
- Show calculated 15 kg crate, wine-liter and bottle projections with the multi-year outlook on the TV Vintage page.
- Record MariaDB as the authoritative operational source while retaining every workbook row as one-time migration evidence; Fatture in Cloud remains authoritative for finance.

## 0.24.31

- Add a configurable 0–6 weather-TV map zoom, with two extra zoom steps retained as the recommended default.
- Expand Mount Etna views with the latest Toulouse VAAC aviation color code, eruption description, ash direction and speed, plume height, forecast windows, remarks, advisory number and next update time.
- Show the transparent Baiamonte logo whenever a configured TV camera is unavailable, still connecting, or fails to load.

## 0.24.30

- Add a Mount Etna workspace and optional rotating TV page backed by official INGV communications, surveillance cameras and the EtnaRCSC seismic catalogue, with Civil Protection, Toulouse VAAC and Smithsonian reference links.
- Add distinct theme-matched monitoring and official-activity animation states, while respecting reduced-motion preferences.
- Create Etna alerts from fresh official activity notices and configured alert delivery preferences without claiming an eruption from unverified secondary data.
- Keep the most recent Etna status available from an offline cache when an official source or the vineyard internet is temporarily unavailable.
- Keep the expanded eleven-page TV menu in two compact rows.

## 0.24.29

- Make the TV Weather page a close Baiamonte precipitation view without aircraft markers or labels; the ADS-B page remains unchanged.
- Add an explicit **Review & update** action for cellar AI suggestions. It opens the existing human-review workflow with editable proposed records before anything is saved.

## 0.24.28

- Normalize saved ADS-B and AIS `/tv` dashboard URLs to their port origin before proxying map HTML, CSS, JavaScript, tiles and status data.

## 0.24.27

- Reset the native ADS-B and AIS application grid in TV map-only mode so the map fills its panel instead of being compressed into the hidden sidebar column.
- Add a dedicated rotating TV Weather page with a large live precipitation map, detailed GW2000 conditions and the Home Assistant forecast.
- Keep the AIS basemap and weather layer visible when vessel reception is unavailable, and normalize saved dashboard URLs so map assets continue loading.
- Show available flag, country, operator/company, callsign, registration, type, ICAO, MMSI and IMO identifiers in the ADS-B and AIS target lists without guessing missing fields.
- Add configurable cellar temperature, fill-level, pH and density guardrails with database, Home Assistant, email and WhatsApp alert routing through the existing alert preferences.
- Add a cellar-focused AI question panel using current readings and guardrails, with enologist safety language and an explicit Send to Review Inbox option before any suggested database update.

## 0.24.26

- Preserve the native ADS-B and AIS map applications on the TV pages so weather layers, map tiles, controls, aircraft icons and vessel flags remain available.
- Add compact target lists, shorter diagnostic lights, two-row TV navigation, overscan spacing and reduced-effects support for Samsung Tizen televisions.
- Add explicit Demo or Live cellar mode, editable demo tank baselines, gently moving demo readings, and consistent cellar views in Vineyard Operations and on the TV.
- Add next-harvest weights, 15 kg crate counts and blend details to the TV Today page.
- Add the latest laboratory sample, measured results, flags and an enologist-controlled suggestion card to Intelligence.
- Add a GW2000 conditions card, Home Assistant forecast and large moving precipitation map to Weather.

## 0.24.25

- Add a configurable 5–1440 minute master refresh that runs all configured Vineyard Operations integrations together, defaulting to hourly.
- Keep faster weather, Gmail, finance and website schedules active between full-system refreshes.
- Add an authenticated manual full-refresh API and record each full cycle in the Processing Log.
- Backfill the new schedule and TV map-brightness defaults for existing installations without replacing saved credentials or choices.

## 0.24.24

- Add a 60–180% TV map-brightness setting for the integrated ADS-B and AIS maps, defaulting to a clearer 125%.
- Keep AIS source timestamps in the configured Rome display time instead of shifting timezone-naive values.

## 0.24.23

- Replace the old embedded aircraft overview with a Baiamonte-styled ADS-B map and compact live target list sourced from port 8998.
- Add a matching AIS vessel map and target-list TV page sourced from port 8999.
- Keep both traffic pages read-only and proxy their local data through the TV service without exposing the source dashboards.

## 0.24.22

- Clear the Processing light after a failed integration is followed by a successful retry; unresolved intake failures remain visible.
- Shorten Today-page service, router, WAN, LAN and power light labels while retaining full diagnostic details in tooltips.

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
