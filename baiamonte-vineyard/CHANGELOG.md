# Changelog

## 1.2.9

- Route the Manager WhatsApp menu's live operational choices through verified MariaDB and Home Assistant snapshots, with concise AI explanation only when the configured assistant is available.
- Default replies to the medium received, retain explicit text, voice and combined preferences, and use saved language, message wording and country code to choose English or Italian.
- Make address-book saves report success independently from a delayed communications refresh and move live WhatsApp snapshot construction into its own domain module.

## 1.2.8

- Give Vineyard Overview a dashboard-outline sidebar icon so Vineyard Operations remains the only grape icon in the Home Assistant left rail.

## 1.2.7

- Replace every visible Vineyard Overview top-bar label with a distinct destination icon while retaining view titles for tooltips and accessibility.
- Align Home, Cameras, Security, Weather, Systems, Harvest, Media and AI navigation with the icon vocabulary already used by the dedicated iPad and administrator dashboards.
- Refresh the editable Home Assistant sidebar icons for Overview and Map while retaining the already-consistent Vineyard Overview and Admin identities.
- Make the mobile vineyard Atlas map recalculate its Leaflet canvas when the hidden view opens, its container resizes or the phone rotates, preventing the persistent partial-tile gray map.

## 1.2.6

- Reorganize Agronomy & Cellar Control around compact task shortcuts for vessel readings, the tank register, wine labels, harvest transfers, treatments and blend planning.
- Collapse the tank register, blend planning and legal-label administration by default while keeping the daily vessel-reading workflow immediately available.
- Separate wine/legal data, label-tablet assignments and retired records into focused expandable sections without changing existing tank-label or print behavior.

## 1.2.5

- Verify the visitor-facing public homepage after each vineyard-feed publish so Website status cannot remain green when only the receiver endpoint is reachable.

## 1.2.4

- Restrict the public vintage feed to Grecanico, Grenache and Nerello Mascalese so internal Blend and Other planning placeholders never appear on the website.
- Keep vineyard hectares and parcel/block counts private while retaining the public vine count; sanitize both newly published and previously stored website payloads.
- Retire the legacy workbook's Blend and Other grape-variety placeholders and cancel only their unapproved scheduled harvest plans while preserving the separate Nerello/Grenache blend-production program.
- Keep Blend and Other out of MCP harvest reports and prevent future workbook imports from recreating either placeholder as a grape variety.

## 1.2.3

- Add complete numbered English and Italian WhatsApp menus for Reception, Reporter and Manager assistants, with deterministic routes for weather, work, harvest, treatments, cellar, cameras, presence, power, traffic and Etna.
- Let contacts change assistant language with ENGLISH, ITALIANO or LANGUAGE AUTO and keep the existing text, voice, both and match-received reply preferences.
- Add an explicit HUMAN/PERSONA handoff, focused clarification prompts and safe next steps whenever a request is unclear, unsupported or missing live data.
- Keep AI outages from generating a new urgent notice for every message: retain the message, record the integration failure and return a concise MENU/HUMAN recovery path.

## 1.2.2

- Reduce Eufy load by increasing the bridge polling interval from 10 to 30 seconds while retaining push-driven events.
- Make TV camera pages reuse the one-at-a-time scheduler's durable snapshots for up to 30 minutes instead of opening new P2P sessions whenever the page appears.
- Refresh camera walls no more than every five minutes, clearly mark older snapshots, and retain the visible last-good image when a refresh fails.
- Keep upstream camera requests serialized with exponential retry backoff so sleeping or offline cameras do not disrupt the rest of the wall.

## 1.2.1

- Add an explicit Red, White or Rosé wine-color choice to manual cellar readings and legal wine profiles, and carry the matching liquid tint through operations, TV and tank-label displays.
- Keep the current administration section and scroll position after successful cellar or tablet saves instead of returning operators to Today.
- Add controlled vineyard contents, cellar stage and legal processing-phase choices, while keeping an explicit Other contents field for exceptional records.
- Add tank renaming, date-based next checks, cantiniere and complete Tenuta Baiamonte legal identity fields to the editable tank register and live/print labels.
- Fix Aging tank saves by migrating all supported vessel types and by mapping manual process stages safely onto the narrower wine-lot lifecycle.
- Add compact payroll totals to Finance and system documentation, show social publishing readiness separately from optional recent-post readback, and improve navigation icons and cellar-card spacing.

## 1.2.0

- Replace the Mac Home Assistant payroll month interaction with a compact inline editor made from ordinary month buttons and a numeric year field. It no longer invokes a native month picker, dialog, focus trap, browser-history transition or page-level scroll lock.
- Split the browser application into focused payroll, messaging, cellar, alerts and harvest modules while preserving the existing routes, API contracts and shared application state. The core `app.js` is reduced from about 362 KB to about 243 KB.
- Introduce matching backend domain boundaries for payroll policy, WhatsApp event handling, cellar migration, alert transitions and harvest blend calculations. Existing call sites retain compatibility aliases so the separation can continue safely in later releases.
- Add assembled-source regression helpers so domain behavior remains covered after extraction, and cache-bust every new module with the packaged add-on version.

## 1.1.12

- Remove placeholder Blend and Other varieties from operational harvest dates, projections and calendar output.
- Keep only the latest power-restoration notice open and clear it after the short recovery window.
- Make the scheduled complete refresh recover only stale sources while preserving a true full refresh for manual runs.
- Align the API and packaged add-on version metadata and add regression coverage for the cleanup behavior.

## 1.1.11

- Remove the monthly payroll action from the native HTML dialog path that still crashed Home Assistant's Mac WebView.
- Open monthly attendance in a lightweight in-page sheet with explicit Month and Year selectors and no modal, autofocus or browser-history transition.
- Keep the same audited monthly-total API and add a regression check that forbids `showModal()` from returning to this action.

## 1.1.10

- Replace the native monthly payroll date picker with stable Month and Year selectors for Home Assistant's embedded Mac browser.
- Preserve the existing `YYYY-MM` monthly attendance record and decimal total-hours workflow without opening a crash-prone native picker.
- Add a regression check that prevents the incompatible monthly input from returning.

## 1.1.9

- Add an authoritative vintage blend program for the three finished wines: 100% Grecanico, Nerello with adjustable Grenache, and the remaining 100% Grenache.
- Calculate the Grenache component as a percentage of the finished Nerello blend, including exact kilograms, 15 kg whole-crate picking target, rounding surplus and available-fruit shortage.
- Switch Today to a live additional-crate target as soon as recorded Nerello picking begins and recalculate it after each Nerello or Grenache harvest lot.
- Add an Agronomy administrator control for blend percentage, crate weight, juice yield and safe tank working fill, plus a non-destructive scenario calculator.
- Show predicted liters, 750 ml bottles, required gross vessel capacity and fitting current tanks for all three wines in Agronomy, Grapes and Projections.

## 1.1.8

- Repair the TV disease-pressure sparklines on Samsung browsers by isolating their tiny 0–100 scale from the large risk-score typography.
- Bound and clip each rolling trend plot inside its card so axis labels and lines cannot overflow into adjacent pressure cards.

## 1.1.7

- Print the selected tank's current live legal label directly from Agronomy & Cellar administration.
- Offer a complete A4 landscape record and a compact high-contrast 4×6-inch UPS-style thermal label.
- Reload the authoritative tank and wine record before opening the browser print dialog so printed labels do not silently use stale admin-form data.

## 1.1.6

- Backfill permanent legal-label tokens for every active cellar tank during startup, including vessels installed before the label service was added.
- Keep all tank and tablet label links on the unauthenticated vineyard VPN endpoint at `http://192.168.0.10:8102`, even when administration is opened through another hostname.

## 1.1.5

- Add a dedicated branded cellar-label kiosk service on port 8102 with one stable, auto-refreshing URL for every active tank.
- Store origin, denomination, vintage, wine type, contents, processing phase, racking history and enologist confirmation with the wine lot so legal identity follows the wine through tank transfers.
- Keep live capacity, volume, level, temperature, density, Brix and pH sourced from each tank's selected manual or sensor mode.
- Retire a tank's live kiosk label without deleting its wine, transfer, legal or audit history, and expose retired labels in a read-only cellar archive.
- Register or retire Android label tablets and reassign each tablet's permanent kiosk URL to a different physical tank without changing the URL saved on the device.
- Present the legal identity in a polished Baiamonte display with the estate logo, restrained cellar motion, animated vessel level and fault-safe last-known readings.

## 1.1.4

- Keep WhatsApp alert delivery reliable for configured recipients, with durable templates, actionable diagnostics and separate delivery evidence.
- Compact the Agronomy & Cellar workspace and preserve the correct physical vessel type, icon and stage animation across the dashboard and TV.
- Fit the TV Today view safely inside Samsung 1080p screens, reduce the harvest-calendar typography and show same-month grape dates as one compact sequence.

## 1.1.3

- Keeps the on-site GW2000 station authoritative and gives delayed observations 48 hours to arrive before using any fallback.
- Replays Home Assistant Recorder history in small scheduled batches and fills only persistent missing days from the labelled Open-Meteo historical archive.
- Prevents fallback observations from overwriting on-site readings or double-counting daily GDD.
- Corrects seasonal GDD and harvest projection selection, recalculates the three grape forecasts, and shows their dates and evidence clearly on the Today and TV views.
- Preserves available historical fields while repairing gaps and reports weather coverage and archive-backfill progress in processing status.

## 1.1.2

- Consolidate legacy individually approved labor rows into one employee/month payment block while preserving each daily record inside its audit detail.
- Show all three authoritative predicted or completed grape harvest dates on TV Today, using the same recommendation priority as Vineyard Operations instead of a stale planned-date field.
- Replace the compressed disease-pressure bar strips with labelled, high-contrast rolling trend lines sized for television viewing.
- Let the agronomist choose each cellar vessel's physical type independently of manual/sensor mode, and carry the selected animated tank, fermenter, aging vessel, barrel, amphora, demijohn, harvest bin or press shape through dashboard and TV views.

## 1.1.1

- Fix the Agronomy & Cellar Control dashboard and related write actions to use the authoritative season ID returned by the shared season helper.

## 1.1.0

- Convert every existing configured cellar vessel into an explicit, editable manual tank while retaining a protected sensor mode for future Home Assistant tank sensors.
- Add the Agronomy & Cellar Control workspace for manual readings, tank creation and safe retirement, maintenance, cellar-stage updates and treatment-program review.
- Trace each picking lot into its cellar lot and current tank, preserving the chain from grape harvest through cellar operations.
- Show all three grape harvest dates or completed picking dates on Today and shorten the Operations and Admin navigation labels.
- Keep sensor entity mapping exclusively in Home Assistant App Configuration; sensor-mode tanks reject accidental manual readings.

## 1.0.47

- Split Apple Reminders into two strict, disjoint desired-state feeds: general work only in **Baiamonte** and planned treatments only in **Baiamonte Treatments**.
- Stop treatment-list imports from republishing into the shared Google/general task store, preventing the round trip that recreated treatment and general reminders together.
- Add explicit cross-list reconciliation output so the Mac sync can remove existing wrong-list copies without approving, applying or otherwise changing a treatment record.

## 1.0.46

- Add a separately monitored **Harvest readiness & projections** schedule that runs after GW2000 history and before calendar/task synchronization.
- Recalculate auditable provisional harvest dates from GDD pace, recent weather, maturity samples, grape labs, phenology, scouting, prior vintages, open work, treatment PHI and available cellar capacity.
- Add an optional evidence-cached AI review with bounded timing adjustments, explicit missing-evidence notes and usage tracking; AI remains decision support and cannot approve or move a protected harvest plan.
- Preserve confirmed, approved, in-progress, completed and held harvest dates while updating only draft or provisional plans in the authoritative database.
- Feed the same current dates into Today, Grapes & Vintage, TV, calendar/tasks, WhatsApp intelligence and the public website, with approved human plans taking precedence over model forecasts.

## 1.0.45

- Capture one genuinely new camera frame every two minutes by default, rotating safely through the configured inventory without opening simultaneous camera streams.
- Keep cached and last-good images available without falsely advancing the timestamp of the last real capture.
- Send manager-only and cistern cameras directly to Home Assistant instead of first requesting the TV-only camera route, and retry one transient Supervisor DNS failure after an outage.

## 1.0.44

- Keep every approved inbound timesheet together as one employee payment block instead of showing a separate payment card for each reported day.
- Provide one audited **Mark block paid** action while retaining the individual dates, hours, notes and reimbursements in an expandable record list.
- Validate that every record in a block belongs to the same employee and source timesheet before recording payment atomically.

## 1.0.43

- Finish applying the Baiamonte login branding before exposing the Home Assistant MCP proxy, so a branding failure cannot leave a partially initialized integration.
- Restore the stock login page without registering the Baiamonte MCP route, and rely on Home Assistant's supported route handling instead of an incompatible custom `OPTIONS` method.

## 1.0.42

- Make the Operations/Admin mode switch use delegated click handling so it remains responsive inside Home Assistant ingress and mobile WebViews.
- Route tab activation through one reliable view controller, including Payroll & Labor, system control, documentation and their data refresh hooks.

## 1.0.41

- Keep stored operational alerts visible even if legacy WhatsApp/email inbox reconciliation encounters a bad record.
- Preserve alert type, source and severity in the Today fallback response, with urgent alerts ordered first.
- Distinguish an alert refresh failure from a healthy system with no active alerts instead of silently showing an empty list.

## 1.0.40

- Put approved legacy Apple Messages and imported labor records with an unresolved payment state into the employee payment queue without changing their recorded hours or worker attribution.
- Keep one source message split into independently editable, approvable and payable worker reviews whenever Giancarlo reports hours for more than one named person.
- Merge a seeded short worker identity such as **Nunzio** into the matching Home Assistant person such as **Nunzio Testa**, keeping one labor card while preserving all aliases, services, hours and payment records.

## 1.0.39

- Let administrators review a timesheet as dated daily lines or as a single monthly total without inventing unsupported work dates.
- Keep unsaved worker, period, hours, notes and reimbursement edits while the dashboard refreshes, and show a prominent labor-plus-expenses total before approval.
- Include imported approved timesheets and linked reimbursements in the worker payment queue, with a separate audited **Mark paid** step.
- Consolidate duplicate labor-person cards by normalized worker name while retaining every underlying labor record.

## 1.0.38

- Add editable reimbursable expense rows to incoming timesheet review for fuel, tools, materials, delivery, services and other verified costs.
- Keep reimbursements separate from labor-hour calculations while linking approved costs to the same employee and unpaid payment queue.
- Treat either the Mac intake API key or the MCP bearer token as a valid Mac/Codex connection, and show the exact missing fields for Facebook and Instagram instead of a generic setup warning.

## 1.0.37

- Exclude entrance, vineyard and Etna camera pages from Pi Zero low-power rotation after the WPE threaded compositor was observed faulting on live camera content; larger kiosks retain every camera page.

## 1.0.36

- Add an administrator-only System documentation page with live service links, ports, safe API references, role summaries and connection readiness while never returning passwords or tokens.
- Start authorized users on Operations → Today on a fresh Vineyard Operations launch; explicit deep links and the dedicated hourly-worker portal continue to open their requested page.

## 1.0.35

- Reduce the Pi Zero clock refresh from every second to every 15 seconds, lowering continuous WebKit layout work while preserving the minute-accurate TV clock.

## 1.0.34

- Make People and Payroll refreshes perform a fresh Home Assistant read, show an exact success count or failure reason, and retain the existing directory when a refresh fails.
- Keep the administrator People and Payroll pages full-width and stable on narrow Apple and Android screens, with one readable person card per row on phones.
- Let hourly and seasonal workers submit one-off services such as water delivery, materials or transport with receipts; review them separately and queue approved charges alongside labor for payment.
- Let an administrator assign retained records from an unidentified part-time worker to the correct named worker without discarding the original labor history or audit trail.
- Restore AIS vessel positions on the TV with a bounded fallback marker layer; live targets remain primary and stale cached positions are clearly faded and labelled as last known instead of silently leaving the map blank.
- Preserve unsaved timesheet edits across background status refreshes so employee selection, dates, hours and notes no longer disappear during approval.
- Add a monthly-total attendance entry for Giancarlo without inventing unsupported daily shifts, while retaining the dated workflow for hourly workers.
- Keep labor-history expansion state across refreshes and compact worker summaries into a denser responsive grid with history opened only when needed.

## 1.0.33

- Keep Pi Zero map frames asleep during the dashboard data refresh as well as initial page load, preventing the refresh from waking every hidden map and blocking page rotation.

## 1.0.32

- Keep hidden live-map frames fully asleep on Pi Zero and load only the map belonging to the visible page, preventing background map rendering from consuming the single CPU core.

## 1.0.31

- Delay hidden ADS-B, AIS and weather map frames on Pi Zero kiosks until the browser needs their dashboard section, improving the first display and reducing unnecessary startup work.

## 1.0.30

- Cache versioned TV styles, scripts, images and proxied map assets so the Pi Zero reuses them instead of downloading them again.
- Automatically use a low-power display mode in Cog/WPE kiosks, removing costly decorative animation while preserving live vineyard data and page rotation.

## 1.0.29

- Recover member rosters for retained WhatsApp groups that are absent from the bulk participating-group response by requesting their metadata individually.
- Keep group rosters current after membership changes and show a clear explanation when WhatsApp retains a group title but no longer exposes its members.

## 1.0.28

- Prioritize every visible WhatsApp group before direct chats when requesting older history, removing the earlier 25-chat cutoff that could exclude group conversations.
- Synchronize and display group participants with resolved contact names and phone identifiers where WhatsApp makes them available.
- Restrict Mac/phone address-book imports to identities already visible in the linked WhatsApp account and remove unrelated address-book rows left by the first importer.

## 1.0.27

- Pair WhatsApp phone-number and LID identities in both directions, remove duplicate contact rows and apply learned names dynamically to retained conversations.
- Import an exported phone address book (`.vcf`) so private phone contact names can be matched to synchronized WhatsApp chats even when the linked-device protocol withholds those names.
- Add downloadable chat backups and a safe relink flow that preserves retained chats, learned names and administrator settings while replacing the linked-device credential.
- Add an unmistakable full-width Save account settings control at the bottom of each system-account card.

## 1.0.26

- Resolve QR-linked WhatsApp LID contacts through phone mappings, contact events, chat titles, group metadata and sender profile names without letting later numeric placeholders overwrite learned names.
- Add explicit prior-chat synchronization with retained history counts, safe append handling that does not re-ingest old messages, and clear relink guidance when WhatsApp did not supply an initial history seed.
- Let administrators name any remaining unresolved linked-account contact directly; saved names persist across refreshes and reconnects.

## 1.0.25

- Keep inbound and outbound WhatsApp health as separate sender-specific status lights, including the latest outbound failure instead of treating any historical send as proof that the selected number works.
- Record the Meta phone-number ID with inbound, text and media events so production and test traffic can no longer contaminate one another's status.
- Persist the selected production or test sender while saving TV and other GUI settings, and keep its matching token, business account and template library active after refreshes and restarts.

## 1.0.24

- Reorganize each linked WhatsApp system account into full-width collapsible Contacts, Groups and Membership sections so names and controls remain readable instead of being squeezed into narrow columns.
- Increase mobile touch targets and stack identity, action, selector and add-contact controls cleanly inside the Home Assistant mobile application.
- Constrain the WhatsApp conversation window to the real viewport, keep it centered, and stack its reply control on narrow screens so dialogs can no longer extend beyond or slide off the page.

## 1.0.23

- Synchronize participating groups and their members immediately after a QR-linked WhatsApp account connects, with a manual **Refresh contacts & groups** control for existing sessions.
- Request the linked account's available recent chat history, contacts and chats, and retain the synchronized catalogue and recent messages across Vineyard Operations restarts.
- Keep historical synchronization read-only while routing only newly received messages from administrator-selected contacts or groups into the existing review-and-approval intake flow.
- Expose catalogue refresh time and errors in Messaging admin, and make selected-group ingestion explicit in the group picker.

## 1.0.22

- Repair QR pairing against the current WhatsApp handshake by using the live WhatsApp Web client version instead of Baileys' stale bundled registration version.
- Upgrade the QR-linked bridge to Baileys 6.7.24, expose the active Web client version and retain the real disconnect status in administrator diagnostics.
- Bound reconnect attempts with backoff so a rejected pairing cannot create a rapid background retry loop.

## 1.0.21

- Add one narrow Home Assistant Cloud HTTPS route for the authenticated Vineyard Operations MCP protocol so managed Codex tasks can reach the server without exposing MariaDB or other add-on ports.
- Preserve the existing MCP bearer-token validation and forward MCP session/protocol headers and streamed responses through the TLS edge.
- Repair QR-linked WhatsApp account startup across the Alpine/Node module export shapes used by the packaged Baileys client, restore QR generation for both independent system accounts and move off the vulnerable 6.7.18 release to patched 6.7.22.

## 1.0.20

- Make the Home Assistant Person record authoritative for each estate team member's name, picture, presence entity and linked Home Assistant user ID.
- Preserve Vineyard Operations as the owner only of estate role, application access, hourly-labor settings and payroll history.
- Reconnect renamed Person entities by stable Home Assistant user ID and conservative username/name aliases so a rename does not create a duplicate worker or detach prior labor history.
- Use the live Home Assistant Person name on the private worker dashboard instead of an older saved profile or add-on display-name value.
## 1.0.19

- Keep a sleeping or temporarily unreachable camera from creating an estate-wide processing error; retain its last good image, rotate it to the back of the refresh queue and retry later.
- Reuse the serialized TV camera endpoint first and the supported Supervisor camera API second, removing obsolete internal camera hostnames that could mask the useful failure with a DNS error.
- Treat a successful authenticated Meta sender lookup as connected even when Meta omits its optional platform type, and distinguish saved configuration from a genuine live connection failure in Messaging admin.

## 1.0.18

- Show the private clock-in workspace only for people explicitly marked as hourly labor in the Estate team profile; other worker and operations accounts keep their normal views.
- Standardize estate roles with an administrator dropdown and reuse the saved role across People, presence, labor and worker context without overwriting existing legacy roles.
- Let authorized operations users mark a planned treatment complete with an actual date and optional completion notes while retaining the plan and immutable audit history.
- Repair the multi-year cellar overlay by ordering vintages, labeling units and redrawing the chart only after its tab or expandable section is visible.
- Replace indefinite worker-profile loading with a clear account assignment state and a safe display-name fallback during profile refresh.
- Add a configurable Camera snapshot cache process that refreshes only the oldest selected camera per run, saves last-good images and honors the existing camera failure backoff.

## 1.0.17

- Keep the Estate team directory names and live details synchronized with Home Assistant Person entities while retaining Vineyard Operations access and labor settings.
- Replace the fragile TV Mount Etna illustration with a Samsung-compatible animated SVG that clearly distinguishes normal monitoring from active conditions.
- Replace raw comma-separated TV camera configuration with a searchable Home Assistant camera selector, availability labels, select-available and clear actions.
- Require an explicit employee selection for each incoming timesheet so a reporter can submit separate hours for themselves and another worker without mixing approvals.
- Open the most recent retained cistern camera image, estimated level, confidence and capture time directly from the Today cistern card.
- Separate treatment forecasts and planned work from verified completed applications, with cancelled or rejected records excluded from the active forecast while retained in full history.

## 1.0.16

- Keep Estate team & presence synchronized with every Home Assistant Person, automatically adding new people to the directory while retaining their live person and tracker entities.
- Add an administrator-owned profile for each person with Home Assistant username, Vineyard Operations access level, estate role and optional hourly-labor tracking.
- Keep finance permission independent from person access levels so Operations and Worker assignments never broaden private finance access.
- Separate the timesheet sender from the employee whose hours are being reviewed, show daily rows and totals compactly, and keep reported expenses outside labor approval.
- Prevent horizontal mobile page drift across every Operations, Admin and worker view and reset stray horizontal position when changing pages.

## 1.0.15

- Let each QR-linked system WhatsApp account interact with all contacts or only administrator-selected contacts, independently for both accounts.
- Enforce the same contact scope for inbound monitoring and outbound messages while keeping group selection separate.
- Keep Meta Business Manager, Reception assistants, templates, webhooks, delivery receipts and review intake isolated from the two linked system accounts.
- Pack the mobile Operations and Admin menus into a continuous three-column flow without empty grid cells between navigation sections.
- Keep worker navigation English-only and remove personal names from the worker welcome header while retaining bilingual work instructions.
- Restrict each worker's waiting-approval records and pay summary to the currently logged-in worker; cross-worker payroll remains available only in the administrator view.
- Personalize the private clock-in card with the authenticated worker's name, waiting hours, approved amount due and paid-to-date totals.
- Replace the oversized administrator labor dump with a compact searchable worker/payment filter, live entry/hour/cost totals and expandable audited rows.
- Give every labor user a compact Apple- and Android-friendly personal workspace with clock-in/out, a live timer, assigned work, editable pending time, expenses, photos, private pay totals and locked history.
- Route the Mattia and Carmela accounts directly to that minimal worker-only dashboard, even if broader account lists are changed later.
- Format manual labor entry as a clear single-employee form and reject mixed-worker timesheet approvals so hours are reviewed and locked per employee.
- Split People, Payroll & labor and System control into independent administrator pages instead of one oversized linked surface.
- Restore the TV display after removing the retired iMessage bridge by repairing the communications payload and serving both `/` and `/tv` on the kiosk port.

## 1.0.14

- Rebuild the mobile header into a compact, stable two-row layout so the Baiamonte brand, year, refresh and menu controls remain fully visible.
- Give the Operations/Admin switch its own full-width row and replace the bulky active-section label with a small gold navigation indicator.

## 1.0.13

- Fix the Home Assistant image build for the QR-linked WhatsApp system accounts by including the Git client required by the Baileys dependency during installation.

## 1.0.12

- Add two independent QR-linked WhatsApp system accounts with persistent sessions, clear linked-state diagnostics and selectable direct chats or groups for ingestion.
- Keep the official Meta Business API entirely separate, including its registered senders, templates, webhooks, assistants, native groups and delivery log.
- Give each system account its own label, direct/group filters, selected-chat list and administrator-controlled send permission; sending is limited to chats already visible on that linked account.
- Triage linked-account messages and attachments through the existing AI review workflow, quietly archive ordinary conversation, retain material vineyard information, and deduplicate overlapping Mac or linked-account intake by sender, time, text and attachment hash.
- Replace the legacy iMessage workspace, routes and webhook with the compact two-account system view.
- Add a synchronized contact book, recent-chat view and explicit administrator approval or rejection for WhatsApp group invitations and pending join requests.
- Move system WhatsApp, Meta Business messaging and social publishing into the Admin navigation and enforce the same administrator boundary on every related read, send, configuration and membership endpoint.
- Keep routine Operations navigation focused on vineyard work, review and decisions while grouping finance, payroll, messaging, publishing, alerts and system controls naturally under Admin.
- Rebuild the TV Work Plan into an action-first board with overdue and today work, a deduplicated seven-day plan and the upcoming Baiamonte calendar; completed and stale items no longer clutter rotation.

## 1.0.11

- Add a simple bilingual Baiamonte worker portal for the existing Giancarlo, Luca, Mattia and Carmela Home Assistant accounts with clock-in/out, current work, work photos and optional expenses.
- Let workers correct submitted or returned time and work details before approval, visibly mark time edits, and retain every change in the audit log.
- Add an administrator queue to compare worker submissions with GPS/person or camera evidence, display an evidence confidence rating, approve and lock records, or return them for correction.
- Queue approved records for payment instead of treating approval as payment, and add one audited **Mark paid** action with due and paid dates.
- Keep approved hours, compensation, payment state and prior history read-only in the worker portal, with MariaDB remaining authoritative for labor reconciliation.
- Reorganize the complete navigation without removing data, including separate administrator and operations modes plus direct Payroll & labor and System control tabs.

## 1.0.10

- Add an administrator timesheet review gate in Operations Control with editable worker, date, hours, rate and work-note rows before approval.
- Cross-reference reported days with retained Home Assistant person, phone/GPS and recognized-camera history as supporting evidence, clearly marking missing telemetry as unknown rather than absence.
- Approve all reviewed daily rows in one transaction, retain exact duplicates without creating another entry, and preserve the source and approval evidence in the audit log.
- Allow audited corrections to existing labor entries directly from worker history and the full labor log, with recalculated labor cost when hours or rate change.

## 1.0.9

- Add compact year-over-year disease and stress screening charts to Treatments, including monthly average and peak lines for every recorded pressure type and expandable prediction evidence.
- Make resolved Issues & Decisions leave the active work list immediately and remain available in a compact resolved/deferred history.
- Compact the Alerts & Inbox workspace while keeping active alerts, review items, filters and full notice details accessible.

## 1.0.8

- Call Home Assistant's write-only Google Tasks services without requesting unsupported response data, allowing existing Vineyard Operations work to publish to the shared Baiamonte task list.

## 1.0.7

- Keep Calendar & Tasks on Home Assistant's supported Supervisor Core proxy and retry short post-restart interruptions instead of falling through to unauthenticated internal hostnames.
- Report a concise actionable planning error only after three failed attempts, without exposing credentials or replacing the original failure with an unrelated DNS message.

## 1.0.5

- Separate per-message WhatsApp delivery and assistant failures from estate-wide integration health, keeping message details in Communications without raising a false vineyard-service outage.
- Keep one live weather, laboratory, overdue-work and cellar-check alert per condition, resolve it when the condition clears, and retire duplicate date-based alerts from earlier releases.
- Give Home Assistant persistent alerts stable IDs and dismiss them when their underlying condition is resolved or acknowledged in Operations Control.
- Automatically archive harmless analyzed messages that contain no vineyard facts, questions, proposed records, or review requirement while retaining their source and audit history.
- Add compact one-tap “No action” and bulk routine-WhatsApp cleanup controls, and replace slow sequential Operations Control error clearing with one transactional request.
- Make Gmail dialog actions reliable through delegated controls and show immediate success or error feedback inside the open message.

## 1.0.4

- Rebuild Finance as a compact review surface with collapsible open-items, inventory, performance and accounting-document sections.
- Add source-backed receivable, payable, VAT, overdue-document, sync-freshness and inventory-count review indicators while keeping Fatture in Cloud authoritative for accounting.
- Add current inventory quantities, bottle totals, stock value, stale-count warnings and a direct inventory-count action without exposing Finance to kiosk or standard users.

## 1.0.3

- Keep qualifying Linguaglossa/Etna earthquakes active for the full Europe/Rome calendar day and reopen the matching alert if an earlier refresh resolved it prematurely.
- Wire the configured WhatsApp test sender into the runtime, retain production and test senders together, and clear recovered DNS/channel transport errors without hiding message-delivery failures.
- Restore Home Assistant's native frontend and authorization route for Companion app sign-in while retaining the full Tenuta Baiamonte browser login treatment.

## 1.0.2

- Retain qualifying nearby earthquakes for the complete Europe/Rome calendar day, normalize INGV FDSN timestamps as explicit UTC, and reopen an event alert if an earlier refresh resolved it prematurely.
- Pass the saved Meta test-sender settings into the app runtime and clear only recovered WhatsApp DNS/transport errors after a successful live connection check, while preserving failed-message audit history.

## 1.0.1

- Upgrade already-versioned Baiamonte login bundles and image assets safely, ensuring mobile browsers actually receive the new cache-busted login after an app update.

## 1.0.0

- Promote Vineyard Operations to its first stable release after a full runtime, database, Home Assistant and TV-display audit.
- Cache the large Home Assistant state inventory briefly and use the Supervisor Core proxy exclusively, reducing repeated work and eliminating invalid fallback authentication attempts.
- Treat temporary cistern-camera and WhatsApp connectivity failures as recoverable monitored conditions, retain the last accepted cistern estimate, retry transient WhatsApp checks and automatically clear recovered alerts.
- Reuse one live cistern or integration-failure alert instead of creating daily duplicates, while preserving resolved audit history.
- Keep the TV disease and stress-pressure grid inside its card at large-screen resolutions.
- Show one Today alert per type, rotate additional alerts of the same type, and slow the alert ticker according to its message length.
- Publish a new cache-busted Baiamonte login handoff that uses Home Assistant's current authorization component and avoids the stale Brotli/gzip frontend path seen on mobile browsers.

## 0.25.32

- Raise a specific intervention alert when the OpenAI API key, quota/credits or token limit blocks analysis, retain the exact safe error and failed feature in Control, and clear the alert after the next successful AI request.

## 0.25.31

- Keep up to three critical Today findings visible together in the red alert rail instead of hiding them behind timed rotation.
- Retain all active alert text in the scrolling ticker when more than three findings exist.
- Detect an unplanned return after a power or host interruption, retain the restoration finding for the day, and notify configured Home Assistant, email and WhatsApp recipients with the measured monitoring gap.
- Keep planned upgrades and Core restarts from producing false power-restoration alerts by recording a graceful shutdown marker.
- Make AI cost control denser and more useful with today's spend, today's requests and tokens, month-to-date spend, month-end projection, budget percentage, average request cost, cache efficiency, feature detail and model rates.

## 0.25.30

- Keep answered WhatsApp questions in Recent Communications while removing them from the TV Needs Review queue.
- Limit Needs Review to genuinely unprocessed items, failed processing, pending approvals and pending manager controls.
- Add live-condition icons, a compact current-weather card and restrained animated weather scenes to the TV Weather page.
- Route the normal Home Assistant sign-in handoff through a fresh cache-busted Baiamonte page, matching the proven Miami Home Assistant behavior while retaining the stock authentication controls.
- Add the Baiamonte icon and logo to the branding integration and give its Home Assistant detail page a clean estate-facing name.

## 0.25.29

- Reconcile every successfully handled WhatsApp notice regardless of the AI classification label, including older camera and weather requests that were misclassified as records.
- Keep generic newsletter and account-email questions out of Priority Notices while retaining their full message and analysis in Communications.

## 0.25.28

- Mark approvals, failures and other exceptions explicitly as Action needed, allowing legacy unmarked question cards to leave Today while remaining available in the Communications history.

## 0.25.27

- Treat Today Priority Notices as an intervention queue: a successfully answered WhatsApp question closes its notice only after the reply is accepted for sending.
- Keep approval requests, failed assistant replies, disabled-review routing, daily-limit exceptions and failed controls visible until a person intervenes.
- Reconcile earlier WhatsApp question notices that already have an approved, rejected, archived or successfully answered disposition without deleting their source messages or audit history.

## 0.25.26

- Prioritize today's Etna and nearby-earthquake records ahead of older critical alerts in the bounded TV payload, so a seismic warning cannot be crowded out by historical cistern or system alerts.
- Rebuild the TV disease and stress card around the lead current risk, 14-day direction, compact comparative scores, recommended field action and visible agronomist-review status.

## 0.25.25

- Retain Etna and nearby-earthquake findings on Today and TV through the full database-local calendar day in which they occurred.
- Mark a cleared condition as a recent event rather than active, while preserving its time, explanation, animation and ticker until the day ends.

## 0.25.24

- Keep current Etna activity and nearby-earthquake findings visible in the TV Today urgent area until the official source condition clears.
- Automatically resolve obsolete Etna and seismic alerts on the next successful official-source refresh instead of leaving stale warnings open.
- Rotate multiple urgent findings without allowing a cistern warning to hide a seismic event, with distinct restrained earthquake and volcanic motion treatments.
- Preserve the original alert description and type in the TV payload so the finding explains what happened and why it remains active.

## 0.25.23

- Restyle the Home Assistant sign-in page with the Baiamonte charcoal, wine and gold visual system while retaining the stock authorization controls.
- Install the required logo assets and enable the guarded branding integration automatically, with a timestamped configuration backup and a single Core restart required.

## 0.25.22

- Switch nearby-earthquake monitoring to the official national INGV FDSN feed and create distance/magnitude-guarded alerts within minutes.
- Show current earthquake and Etna notices with restrained siren beacons and scrolling alert text on Today, Etna, and TV pages.
- Add a safe “Flush completed” intake action that archives approved and rejected items, clears them from active/TV views, and retains source files and audit history.
- Populate the WhatsApp Manager camera selector from the live Home Assistant camera catalog and provide a one-click TV/default selection.
- Add the Mobile Safari-tested Tenuta Baiamonte login treatment while preserving Home Assistant's stock authorization component.
- Keep an atomic stock-page backup and refuse to patch an unknown frontend layout.

## 0.25.21

- Fixes upgrades from `0.25.19` by making the newly added Meta test WhatsApp Business Account ID backward-compatible with existing saved app options.
- Preserves the configured production WhatsApp sender and all existing credentials while allowing the optional test sender to remain unset.

## 0.25.20

- Separates production and Meta test WhatsApp credentials, accounts, senders and template catalogs so either registered number can be selected without crossing tokens or templates.
- Gives supported inbound WhatsApp messages an auditable response path, bilingual capability menu and configurable text, voice, both or match-inbound replies.
- Expands the authorized Manager assistant with disease/stress intelligence, latest laboratory findings, cistern estimates, AIS/ADS-B status, safe device/camera access and conservative team-presence answers based only on fresh evidence.
- Adds WhatsApp connection and catalog refresh to Operations Control and repairs the TV AIS bridge so valid scoped vessel targets remain visible.

## 0.25.19

- Makes received Gmail, WhatsApp, and iMessage entries expandable so the original message and AI analysis can be inspected without leaving Communications.
- Shows the recorded reason, reviewer, and review time on rejected intake items, with an explicit historical fallback when older records have no saved reason.
- Requires a reason for every new rejection from the review interface and accepts an optional reason after WhatsApp `REJECT` or `RIFIUTA` approval codes.
- Adds a database migration that preserves rejection explanations as part of the authoritative intake audit trail.

## 0.25.18

- Replaces the stylized striped rain with a subtle depth-based canvas rain field and low mist on Vineyard Operations and the TV Today page.
- Repairs Samsung TV remote handling across the main display and embedded pages with keydown/keyup support, Tizen key registration, focus recovery, and duplicate-press protection.
- Keeps the production WhatsApp sender and the Meta test sender available together, clearly marks the test number, and allows administrators to switch without overwriting either configuration.
- Adds a secure bilingual camera command backend for approved WhatsApp Manager contacts, including camera listing, natural name matching, live snapshots, clearly labeled cached fallback images, throttling, and an audit log.

## 0.25.17

- Replaces the simple Today-page weather stripes with layered, condition-driven rain, drizzle, downpour, storm, fog, cloud, clear-sky, clear-night, snow, sleet, hail, and wind scenes.
- Applies the same live Home Assistant weather atmosphere to the rotating TV Today display, with mobile, Samsung TV, and reduced-motion safeguards.
- Distinguishes a verified WhatsApp phone from one fully registered to Cloud API, exposing the registration state and a specific corrective diagnostic instead of a misleading healthy status.

## 0.25.16

- Repairs the administrator person-detail window so it remains centered within desktop, tablet, phone, and Home Assistant ingress viewports without horizontal clipping.
- Adds a compact device, coordinate, GPS accuracy, source, and update summary above the person map.
- Keeps the close control visible while scrolling and organizes complete Home Assistant person, phone/GPS, and camera attributes into readable expandable sections.

## 0.25.15

- Keeps Luca as year-round hourly labor and adds Carmella, Mattia, Nunzio, and both historically unidentified part-time workers as seasonal hourly labor.
- Shows each seasonal worker's preserved historical entries, annual totals, daily drill-down, correction control, and full audit log directly in Labor Reconciliation.
- Retains Giancarlo's monthly attendance model and leaves historical worker names unchanged rather than silently reassigning records.

## 0.25.14

- Rebuilds administrator people management as a compact directory with live presence, location map popups, phone/GPS entity data, full timestamps, Home Assistant attributes, and matching camera-recognition state.
- Replaces the awkward labor and inbox links with working administrator controls.
- Expands Giancarlo and Luca reconciliation from a 62-day window to all named historical records, including annual summaries, daily drill-down, the full underlying labor log, correction entry controls, and a separate unassigned-history list so legacy names are never silently reassigned.
- Adds compact Home Assistant person tiles with native detail popups to the Admin User Tracking dashboard.

## 0.25.12

- Ignores stale unavailable router entities discovered from replaced integrations unless an administrator explicitly selects them for monitoring.

## 0.25.11

- Omits unused auto-discovered router ports from the estate alarm summary while preserving any port explicitly selected by the administrator.

## 0.25.10

- Stops unused LAN ports and healthy `problem=off` sensors from creating false red network alarms.
- Prefers a live internet-link or connectivity sensor over an obsolete unavailable WAN entity for the LTE status light.
- Excludes unrelated Miami network entities from the Baiamonte estate health summary.
- Preserves Meta's useful WhatsApp API explanation in the processing log instead of recording only a generic HTTP 400 error.

## 0.25.09

- Opens the labor-hours entry form directly from the administrator People dashboard instead of landing on the general Work page.
- Keeps the reconciliation deep link focused on the compact Giancarlo and Luca labor panel.
- Treats seven-hour-old Person states as stale and uncertain rather than showing a false green on-site status.

## 0.25.08

- Prevents stale Home Assistant Person/GPS states from showing someone as on site.
- Requires Person/GPS evidence within 45 minutes or matching camera identity within 30 minutes; otherwise the status is amber and uncertain.

## 0.25.07

- Replaces unreliable ingress query-string links with Home Assistant deep paths for Reconcile Labor and Add Labor Hours.
- Removes the labor explanation and account-routing table from the People page, including the requested Finance access note.
- Uses three balanced columns for the map, on-site lights and labor actions to eliminate the unused right-side space.

## 0.25.06

- Resolves Giancarlo and Luca's simple on-site status from Home Assistant Person/GPS state or a matching Eufy identity seen within 30 minutes.
- Shows only the resulting On site, Away or Uncertain light; raw GPS and camera evidence remains hidden.

## 0.25.05

- Adds clear green on-site, gray away and amber unknown status lights to the compact administrator People view.
- Uses only the current Home Assistant Person state; detailed GPS, Wi-Fi and camera evidence remains hidden.

## 0.25.04

- Compacts the administrator People dashboard into two balanced columns and removes the detailed phone, Wi-Fi and camera presence-evidence panels.
- Keeps current person status and annual recorded labor hours visible while limiting daily drill-down to work records and payment status.
- Repairs the Reconcile Labor route, focuses the labor panel after navigation and refreshes Operations Control while its actual view is open.
- Keeps Giancarlo's monthly prior-month payment rule and Luca's hourly invoice workflow explicit in the compact reconciliation view.

## 0.25.03

- Records Giancarlo as monthly-paid on the 15th for the prior month while retaining hours only for attendance reconciliation.
- Records Luca as an hourly contractor whose invoice arrives on an undetermined schedule.
- Prefills labor adjustments with the correct payroll category and role for each person.

## 0.25.02

- Adds compact, drill-down labor reconciliation for Giancarlo and Luca with today, seven-day and monthly recorded totals.
- Keeps payable labor records separate from supporting phone GPS, vineyard Wi-Fi and Eufy recognition evidence.
- Adds prefilled missing-time/correction entry actions without silently overwriting or inferring payroll hours.
- Adds live Eufy identity sensors and phone tracking to the Admin user-tracking dashboard; vineyard Wi-Fi remains clearly marked for commissioning.
- Reformats Solcast P10/P50/P90 cards for readable Cloudier, Most likely and Sunnier columns.
- Removes obsolete Baiamonte helper references from Admin dashboards so missing-entity warning blocks no longer obscure system status.

## 0.25.01

- Fixes the live `system/status` and Operations Control 500 errors by making error-acknowledgement comparisons safe across upgraded MariaDB collations.
- Restores the TV display payload, which shares the same system-status calculation.
- Corrects Giancarlo's live Home Assistant Person entity to `person.giancarlo` throughout the administrator map, presence list and history.
- Improves administrator location details with phone/tracker name, battery and charging state when available, GPS accuracy and last-report age.
- Adds subtle live rain, storm, fog, cloud, clear-sky, snow, hail and wind motion to the Today views in Vineyard Operations and the TV display, with reduced-motion support.
- Corrects the error-clear refresh request to use the real system-status endpoint.

## 0.25.00

- Fixes missing Today solar predictions by discovering renamed Solcast entities instead of requiring one exact Home Assistant entity prefix.
- Adds the genuine Solcast P10/P50/P90 possibility envelope, remaining-today and tomorrow energy, and detailed cloudier/likely/sunnier power curves without generating artificial uncertainty values.
- Adds consistent solar outlook cards to Vineyard Operations, the TV Today page, Vineyard Overview, the iPad dashboard, Display Panel and administrator solar view.
- Adds a dedicated, GitHub-managed **Baiamonte iPad** dashboard at `/vineyard-ipad/home` for the `ipad` Home Assistant account.
- Uses the larger iPad screen for live weather, Growatt and Solcast solar, estate load, safe circuit and lighting controls, cameras, security, vineyard operations, media and AI access while keeping Finance excluded.
- Keeps `ipad` as a built-in read-only Vineyard Operations viewer even when an upgraded installation still has the older saved viewer list.
- Documents the one-time Home Assistant default-dashboard selection that makes the iPad account open directly to its assigned interface.
- Expands the administrator dashboard with dedicated Operations and Devices views, processing and recovery links, communications and database controls, inventory and maintenance entry points, stronger network/LTE monitoring, actual-versus-forecast solar, and cistern/camera safety status.
- Adds an administrator-only **User Tracking** view with the latest Home Assistant person locations on a map, tracker source and accuracy, last-update age, seven-day presence history, role guidance and dashboard routing controls.
- Resolves the dedicated `display` and `ipad` Home Assistant user IDs during dashboard installation and limits each device dashboard's views to its matching account.
- Removes obsolete hard-coded user IDs from Vineyard Overview so current standard vineyard users receive the shared dashboard consistently; Finance remains protected separately inside Vineyard Operations.
- Excludes the `mqtt` service login from person tracking and dashboard routing, and documents that its redundant Home Assistant Person profile should be removed without deleting the working login.

## 0.24.99

- Corrects the MariaDB collation of the new error-acknowledgement table so live display and system-status queries work with the established vineyard schema.

## 0.24.98

- Separates live Growatt generation from Solcast prediction and displays the source clearly on Vineyard Operations and the TV Today page.
- Adds a read-only Home Assistant inventory in Operations Control with device/entity totals, functional categories, unavailable entities and missing dashboard references.
- Adds safe error acknowledgement controls for individual or visible failures while retaining the complete immutable processing audit trail.
- Stops resolved integration failures and acknowledged errors from keeping the current Errors indicator red.

## 0.24.97

- Removes the obsolete `sensor.baiamonte_harvest` dependency from the managed Vineyard Overview and Display Panel dashboards.
- Replaces the broken harvest tile with direct links to the authoritative Grapes & Vintage view and the compact harvest-entry workflow.

## 0.24.96

- Separates active Processing from unresolved Errors across Vineyard Operations, Operations Control, the TV display and the MCP `processing_status` tool.
- Shows real running jobs, prevents duplicate manual runs and records a clear timeout after three minutes while keeping the underlying worker visible until it exits.
- Adds current-error hover, keyboard-focus and tap details to the Today status lights, with the full recovery list remaining in Operations Control.
- Refreshes live system status every 15 seconds so running and error indicators clear without reloading the whole dashboard.

## 0.24.95

- Compacts Operations Control and reports website publishing from a recent successful cycle instead of treating a saved URL as online.
- Upgrades Gmail to a normal message view with sender address, date and time, message size, visible Inbox/Junk/Trash folders, one-tap Junk/Trash actions, and a sticky open-message toolbar.
- Removes aircraft from both weather-map presentations, adds LTE health to system and TV status, and adds live/day/predicted solar input to Today.
- Makes the atlas resilient to a primary Leaflet CDN failure, parses legitimate map-link coordinates, lists unmapped parcels explicitly, and keeps satellite tools available.
- Adds pre-harvest multi-year variety and cellar-process overlays so readiness and conversion history remain useful before the first picking lot.

## 0.24.94

- Adds a read-only **Communications** page to the automatic TV rotation with Gmail, WhatsApp and iMessage channel health.
- Shows compact 24-hour message counts, recent sender-safe summaries, review-queue items and delivery or processing alerts at a glance.
- Keeps full message bodies, addresses and protected credentials off the public display while linking the live view to the authoritative database intake records.
- Completes the TV navigation as an even two-row, six-column layout for Samsung displays.
- Restores reliable Samsung remote control by registering Tizen media/channel keys, capturing directional keys before browser focus navigation, recovering focus after page resumes and showing brief on-screen command feedback.

## 0.24.93

- Adds a one-tap, recoverable **Move to Trash** control to every Gmail inbox row, plus Junk classification and restore-to-Inbox controls.
- Allows permanent deletion only from the Trash folder, behind an explicit confirmation, and records every mailbox action in the audit log.
- Verifies Facebook and Instagram against Meta live instead of treating entered credentials as a successful connection.
- Discovers the Page-specific access token and linked Instagram professional account from Meta, reuses the protected permanent Meta/WhatsApp system-user token when appropriate, and never exposes tokens to the browser.
- Adds Facebook image publishing, Instagram media-readiness checks, clear connection diagnostics and recent social publishing success/failure history.

## 0.24.92

- Makes the WhatsApp address book substantially more compact: contacts are short scan-friendly rows with editing hidden until tapped.
- Improves mobile organization while keeping role, assistant access, activity and invitation actions readily available.
- Makes Check connections show a persistent result with sender, number, inbound, outbound and template-library status.
- Adds a Text + voice reply preference so a contact can receive both the readable answer and the spoken version.

## 0.24.91

- Sends administrator invitations through an explicitly selected, Meta-approved WhatsApp template so Baiamonte can initiate a conversation legally outside the 24-hour customer-service window.
- Verifies the template name, language and approved status against the live Meta catalog before sending, and gives clear mobile guidance when no approved template is available.

## 0.24.90

- Adds an administrator-only WhatsApp sender selector that loads every registered number directly from the configured Meta business account without exposing access tokens.
- Keeps the selected production Phone Number ID in the app data volume so future add-on updates do not revert to Meta's test sender.
- Applies the selected sender consistently to normal messages, attachments, alerts and native groups, with immediate connection diagnostics after a change.

## 0.24.89

- Corrects the Manager and Reporter WhatsApp assistants to read alerts from the authoritative `alerts` table used by this installation.
- Records assistant reply failures in the processing log and sends the approved contact a brief bilingual failure notice instead of leaving a background-task exception.
- Keeps short conversational prompts such as **Vineyard weather** in the chatbot instead of incorrectly creating an APPROVE / REJECT intake item; explicit reports and measured updates still enter review.
- Adds contact activity indicators for an open 24-hour conversation window, recent Baiamonte message activity and the latest delivery/read state. Meta does not expose true online or last-seen presence.
- Supervises webhook background work so failures are logged and cleanly cancelled during shutdown, and repairs fallback IDs for group and iMessage events.
- Restricts trusted Home Assistant identity headers to Supervisor-network requests and limits the TV camera proxy to configured cameras.
- Adds shared TV payload caching, slower traffic summary polling and camera retry backoff to reduce repeated MariaDB, AIS/ADS-B and camera requests.
- Tightens the Contacts page and notices for phone screens.
- Adds focused regression tests for bilingual question-versus-record routing.

## 0.24.88

- Adds a dedicated **Contacts** tab to Messages instead of burying WhatsApp contacts inside the channel panel.
- Replaces the compressed contact rows with readable cards for name, number, vineyard role, AI access, language and text/voice replies.
- Adds contact search and a direct **Send invitation** action on every saved Reporter or Manager contact.
- Shows all saved contacts in the administrator invitation selector and clearly identifies contacts that must first be assigned Reporter or Manager access.
- Gives Manager contacts live read access to Home Assistant solar, battery, grid, inverter, energy and allow-listed device states.
- Adds administrator selection of ordinary Home Assistant devices a Manager may switch only after a one-time confirmation; safety-critical equipment remains excluded and Reporter contacts receive no Home Assistant access.

## 0.24.87

- Keeps hidden administrator-only messaging forms fully hidden in direct-port and non-admin sessions while retaining server-side authorization.
- Shortens the Messages-page voice description while preserving the required compact AI identification on spoken replies.

## 0.24.86

- Moves WhatsApp and iMessage onto a dedicated **Messages** page, leaving Gmail and its mailbox controls in the Inbox.
- Adds separate bilingual **Reception** and **Manager** WhatsApp assistants with per-contact Automatic, English or Italian replies and explicit AI Off, Reception, Reporter or Manager assignments.
- Limits Reception to public harvest and current weather information; Manager receives selected operational context but never finance, credentials, camera URLs or security details.
- Lets approved Reporter and Manager contacts submit text, photos, documents and voice notes into the review workflow, with bilingual `APPROVE` / `APPROVA` and `REJECT` / `RIFIUTA` confirmation codes.
- Adds optional text or spoken WhatsApp replies and English/Italian voice-note transcription for approved contacts; unknown audio remains human-review-only.
- Uses a warm female-style Marin voice by default, adds a simple voice selector, and keeps the AI label compact on voice replies.
- Adds single-use bilingual confirmation codes for allow-listed data refreshes while excluding gates, doors, pumps, treatments and every other physical control.
- Adds an administrator-only invitation action that sends approved Reporter or Manager contacts bilingual instructions for questions, voice, submissions, approvals and confirmed controls.

## 0.24.85

- Replaces the full mobile navigation wall with a compact current-section bar and an accessible expandable menu while preserving every permitted Vineyard Operations page.
- Tightens the mobile brand header, vintage and refresh controls, Today hero, weather summary and urgent finding card so field information appears sooner with less scrolling.

## 0.24.84

- Adds a visible WhatsApp address book for names, international numbers and vineyard roles; known inbound senders appear immediately and new direct-message senders are saved automatically.
- Preserves Meta's exact outbound receipt progression and displays accepted, sent, delivered, read and failed states with WhatsApp-style checkmarks, including historical receipts already captured by the webhook.
- Adds official Meta Groups API discovery, eligibility diagnostics, invite-only group creation, invite-link retrieval, two-way group text/media sending and group-aware inbound review processing.
- Keeps private delivery lists available while clearly distinguishing them from Meta API-managed two-way groups.

## 0.24.83

- Normalizes Meta WhatsApp delivery receipts to the database integration status vocabulary while retaining the exact `sent`, `delivered`, `read`, or `failed` state in the audit payload.
- Prevents delivery-status callbacks from returning HTTP 500 and blocking inbound WhatsApp messages from reaching the review inbox.

## 0.24.82

- Makes **Check connections** perform a fresh Meta WhatsApp sender and template check instead of returning the five-minute cached result.
- Shows an in-progress state and a clear success or failure notice so the connection control no longer appears unresponsive.

## 0.24.81

- Fixes the Operations Control 500 error by registering the Google planning process and making future process lookups fail safely.
- Replaces the Atlas placeholder map with a satellite-first interactive Baiamonte estate map, parcel and block overlays, layer selection, fit, recenter, fullscreen, and parcel-detail tools.
- Keeps a satellite fallback centered on Baiamonte when the interactive map library is unavailable and keeps the estate visible before all parcel boundaries are entered.
- Extends stage-aware tank animation to the Vineyard Operations cellar so fermentation, ageing, settling, transfers, and resting vessels move consistently with the TV cellar display.

## 0.24.80

- Uses a Home Assistant 2026.8-compatible serializable text field for the WhatsApp bridge endpoint while preserving strict URL validation after submission.

## 0.24.79

- Fixes the Baiamonte WhatsApp Bridge setup form on Home Assistant 2026.8 by using Home Assistant's serializable URL schema.
- Keeps the stricter Vineyard Operations webhook-path check when the form is submitted.

## 0.24.78

- Adds the branded Baiamonte WhatsApp Bridge custom integration for Nabu Casa subscribers.
- Provisions a public Home Assistant Cloud callback that supports Meta's GET verification and signed POST delivery.
- Relays the exact request body and signature to the existing Vineyard Operations processor without duplicating WhatsApp credentials.
- Adds a Home Assistant status entity with the callback URL, latest delivery time, HTTP result and relay error.
- Installs managed custom integrations safely with timestamped, recoverable backups.

## 0.24.77

- Keeps each managed Home Assistant camera card on its latest event image when available and installs the transparent Baiamonte logo as the standard offline fallback.
- Publishes the latest successful cistern still into Home Assistant's local camera cache; the camera page keeps that frame during an outage and starts with the logo until the first successful capture.
- Extends the TV aircraft and vessel target-size controls down to 20 percent for close local map views.

## 0.24.75

- Replaces the overloaded Today status strip with readable service, network, and power summaries while still surfacing individual problems.

## 0.24.74

- Replaces the tiny Today status captions with larger, high-contrast status pills: a prominent state light, short service name, and essential value.

## 0.24.73

- Keeps all six Today summary cards, including the cistern camera estimate, in one compact row on the TV display.

## 0.24.72

- Keeps the TV AIS count and vessel rail synchronized with the fresh contacts actually visible in the embedded Sicily map.
- Shows an empty in-view state while the map is loading instead of briefly listing the entire cached AIS feed.
- Adds a compact urgent finding panel to TV Today, prioritizing low cistern with the latest camera image and then other critical vineyard alerts.
- Loads the native ADS-B TV route so saved zoom settings work, and extends both traffic target-size controls down to 30%.
- Keeps Today system and power indicators in one compact top row.
- Explains directly on Grapes & Readiness which authoritative plan, history, laboratory, weather and approved field inputs underpin the working outlook.
- Animates cellar vessels by recorded process stage—fermentation, aging, settling, transfer or resting—while preserving each configured container shape and level.
- Forces an immediate camera refresh whenever Entrance or Vineyard is opened, rather than allowing one camera page's refresh interval to leave the other page on placeholders.

## 0.24.71

- Saves successful TV camera stills on disk and falls back to the last image across camera outages and app restarts.
- Clearly labels fallback frames with their age so a stale image can never look live.
- Lets the native AIS and ADS-B apps apply saved TV zoom controls without a second zoom adjustment.

## 0.24.70

- Extends ADS-B and AIS TV zoom controls to +20 and applies the saved close view directly after each embedded map is ready.
- Adds Fit all, Local view and Very close presets while preserving independent map fine-tuning.
- Seeds the existing Baiamonte coordinates from the maintained Home Assistant dashboards when the database estate location is blank, so the Atlas physical map opens immediately.

## 0.24.69

- Adds a compact urgent-finding strip to Today, prioritizing a low-cistern warning with the latest saved camera finding, percentage, confidence and immediate action.
- Creates a persistent cistern alert below 10% and stores one lightweight snapshot from the existing scheduled AI check, without adding another live camera request.
- Adds a physical estate map to the Vineyard Atlas using OpenStreetMap plus authoritative parcel pins, parcel boundaries and existing block GeoJSON from the database.
- Adds a simple parcel map editor for verified coordinates, direct cadastral links and GeoJSON boundaries so the database becomes the authoritative vineyard map without extra paperwork.

## 0.24.68

- Removes the missing Cistern 360 camera-enable switch from both maintained dashboard sources.
- Retires the old port 8080 aircraft table and map from the legacy dashboard source so a future import cannot restore the dead feed.
- Keeps the current Baiamonte ADS-B app as the single aircraft display path.

## 0.24.67

- Redesigns Today as a compact operational briefing with a weather hero, six at-a-glance vineyard metrics and clearer visual hierarchy.
- Keeps essential service lights visible while moving the complete equipment and network list into an expandable diagnostic section.
- Places next work and recent work side by side on larger screens, reduces the Today alert list to the three highest-priority notices and links directly to the full inbox.

## 0.24.66

- Replaces the unreliable More dropdown with a permanent two-row navigation bar.
- Keeps every permitted page directly visible using shorter, clearer labels that adapt across desktop, tablet and phone widths.
- Removes the now-unused dropdown script and styling.

## 0.24.65

- Adds six zoom-out steps and twelve closer zoom-in steps to both ADS-B and AIS TV maps.
- Keeps map zoom and aircraft/vessel target-size controls independent.

## 0.24.64

- Protects the Eufy bridge by loading TV camera tiles sequentially, preventing overlapping refreshes and stopping immediately when the camera page is hidden.
- Caches each camera still for 90 seconds, permits only one Home Assistant camera-proxy capture at a time and serves the last good frame during brief Eufy outages.
- Keeps TV camera refreshes at 60 seconds or slower and avoids rebuilding unchanged camera walls during ordinary display-data updates.
- Removes the retired port 8080 aircraft table from Vineyard Overview and routes aircraft viewing to the dedicated Baiamonte ADS-B app.

## 0.24.63

- Keeps opened Gmail messages inside a responsive, scrollable dialog so long subjects, addresses, and message bodies cannot distort the page.
- Scans recent inbound Gmail independently of read/unread state, stores the message body plus every attachment, and automatically analyzes a small queue each cycle.
- Adds Today/Inbox alerts for new mail and important classified content, with a direct Review & approve action and a prefilled final-save form.
- Adds outbound photo/document attachments for Gmail, WhatsApp, and the iMessage relay, plus inbound WhatsApp and iMessage media ingestion.
- Drafts replies to inbound vineyard questions from current operational context and exposes a Prepare reply action for human review; nothing is sent automatically.
- Preserves every analyte from an incoming lab report in one reviewable sample and saves the approved result set together.
- Simplifies the two-row top navigation and moves less-used administration, social, history, and record pages under More.

## 0.24.62

- Saves TV settings in the Vineyard Operations persistent data directory, so the GUI works even when Home Assistant does not expose a Supervisor token.
- Continues to synchronize TV settings to Home Assistant app options when Supervisor access is available.
- Completes runtime environment mapping for the independent AIS/ADS-B target sizes and the new WhatsApp and iMessage settings.

## 0.24.61

- Replaces the WhatsApp configuration-only light with a live Meta sender check that shows the real connection error, verified sender and quality state.
- Adds approved WhatsApp templates, delivery-state tracking, contact management, named private delivery lists and opt-in native Meta group IDs for eligible WhatsApp business accounts.
- Adds a full Gmail mailbox view with folders, unread/starred filters, safe plain-text opening, attachment and EML downloads, read/unread, star, archive and recoverable Trash actions.
- Adds an optional iMessage channel through a dedicated Baiamonte Apple Account on a Mac relay, including health, conversations, sending, inbound review and an optional strict handle allowlist.
- Adds independent aircraft and vessel target-size controls to TV Settings, separate from ADS-B/AIS map zoom and brightness.

## 0.24.60

- Adds an administrator-only TV Config page for display timing, refresh interval, theme, controls, camera membership, airport and Etna visibility.
- Adds independent fit-to-detail zoom controls for the native ADS-B, AIS and precipitation maps plus the existing shared map-brightness control.
- Adds a compact Gmail and WhatsApp communication center with received and sent views, explicit sending, and a small vineyard contact list.
- Adds Facebook and Instagram Page management with recent-post views, explicit publishing and metadata-only success/error audit entries.
- Adds targeted error retry and a complete recovery sweep to Operations Control, preserving the original processing audit history.
- Reorganizes Alerts & Inbox into shorter filtered work queues and collapses long notices behind an optional full-detail view.
- Expands Laboratory with annual averages, sampling coverage, flagged-result share and measured-range charts across vintages.

## 0.24.59

- Adds an Operations Control AI cost estimator using API-reported input, cached-input and output tokens, with monthly projection, budget warning, and feature breakdown.
- Adds compact runtime, storage, attachment, recent-error, review-age and setup diagnostics for the system administrator.
- Adds a guided Mac Codex MCP setup panel; the authenticated local/VPN MCP network port remains closed until the administrator explicitly exposes it.
- Allows the vineyard Home Assistant address in MCP host protection while preserving the bearer-token requirement.
- Fixes schedule interval saves failing with HTTP 500 by adding the internal processing-event direction used by the control page.
- Begins auditable AI usage tracking for cistern images, intake documents/photos and vineyard decision-support questions.

## 0.24.58

- Consolidates every internal recurring job under one database-backed scheduler, removing the separate website-publishing loop and duplicate publishing audit entries.
- Gives the cistern camera estimate its own visible schedule, health state, interval and run-now control instead of hiding it inside weather refreshes.
- Organizes the scheduler into System, Sources, Intelligence and Publishing responsibilities with a clear description and one owner for every job.
- Removes the remaining disease-pressure recalculation from Treatments page loads; disease and stress assessment now runs only on its configured schedule or by explicit Run now.
- Keeps the complete-system refresh as the recovery and consistency sweep while preserving independent source intervals and safe minimums.

## 0.24.57

- Adds a private Operations Control page for `rahamin` with live connection lights, process health, last and next run times, safe run-now controls, pause/resume, and adjustable update intervals.
- Moves the continuous weather, Gmail, finance, Etna, traffic, disease, alert, website and complete-refresh schedules into database-backed controls with guarded minimum intervals.
- Adds a consolidated processing audit and review-queue summary so failed, stale, pending and completed updates are visible from one place.
- Adds direct Operations Control and Review Inbox buttons to the GitHub-managed Baiamonte Admin dashboard.
- Adds an authenticated Mac/Codex intake endpoint that deduplicates text updates and sends them through AI analysis and human review without silently changing authoritative records.
- Adds MCP tools for reading process health and safely queuing sourced Mac/ChatGPT items for review, separate from confirmed authoritative-record writes.
- Stops recalculating disease pressure on every page load; the scheduler now maintains the current rolling assessment and records each refresh in the audit trail.

## 0.24.56

- Reduces AIS vessel symbols by about 30 percent on the embedded TV map so dense coastal traffic no longer overwhelms Sicily.
- Makes floating vessel labels shorter and more compact while retaining the dark high-contrast treatment.
- Tightens the right-side vessel cards so more live contacts fit comfortably on a 32-inch display.

## 0.24.55

- Replaces pale AIS map callouts with opaque charcoal vessel labels, warm-white text, gold/type accents and stronger TV-distance contrast.
- Restyles the Vineyard TV vessel list as compact individual dark cards with clearer flags, identity, speed, destination and distance grouping.
- Forces the embedded AIS map labels into the Baiamonte dark theme even when the AIS browser has retained an older cached stylesheet.

## 0.24.54

- Prevents scheduled and manual full-system refreshes from overlapping, avoiding duplicate database, Home Assistant and external API work.
- Runs derived disease, traffic and operational-alert calculations every five minutes instead of rebuilding unchanged results every minute.
- Keeps the dedicated website publisher as the single scheduled harvest-feed publisher while manual full refreshes can still publish immediately.
- Pauses hidden TV-page polling, prevents overlapping display and traffic requests, and resumes with one fresh update when the screen becomes visible.
- Stops the hidden Mount Etna dashboard tab from polling while preserving an immediate refresh when opened.
- Completes background-task cancellation cleanly during add-on shutdown and updates.

## 0.24.53

- Locks the Vineyard TV AIS map and target list to the Baiamonte Sicily area instead of using the combined Sicily and Miami status feed.
- Filters AIS contacts by their assigned area, with a Sicily-bounds fallback for older contacts that do not yet include an area identifier.
- Opens the native AIS TV map with an explicit Baiamonte area so saved Miami choices cannot affect the vineyard display.

## 0.24.52

- Adds a compact on-screen TV control panel with direct page selection, map brightness, rotation timing, refresh and configured-default reset.
- Adds previous, pause/resume and next controls to every TV page while retaining fullscreen and the two-row direct page menu.
- Supports Samsung remote Arrow, Channel, Rewind/Fast-forward, Play/Pause, Back/Menu and Red/Home keys across the main display and embedded ADS-B, AIS and weather maps.
- Stores TV-specific brightness and rotation choices only in that kiosk browser; Vineyard Operations data remains view-only.

## 0.24.51

- Completes browser light/dark integration for Vineyard Operations and contractor entry, including matching browser chrome and native form controls.
- Aligns the Vineyard Operations color contract with the ADS-B and AIS dashboards while keeping the TV display intentionally dark and its traffic maps bright.

## 0.24.50

- Include the add-on manifest inside the runtime image so dashboard and TV asset cache keys use the exact installed release number instead of the development fallback.

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
## 1.0.6

- Extends the bilingual WhatsApp Manager and Reporter assistants across the unified work plan, projects/tasks, operational calendar, Italian holidays, planned treatments, harvest projections, recorded contractor hours, alerts, labs, cellar, cistern, traffic and approved Home Assistant context.
- Classifies explicit WhatsApp project/task submissions for the existing human review workflow; chat never directly approves treatment application or silently changes authoritative records.
- Stops an omitted Meta `platform_type` field from falsely marking an otherwise authenticated WhatsApp sender as unregistered; real outbound failures remain visible and actionable.

- Combines projects and tasks into one compact Work plan, with project/category grouping instead of two competing task surfaces.
- Makes the configured Baiamonte Google Tasks entity the shared team store while MariaDB retains the canonical operational record, source links, and audit history.
- Adds MCP work-plan and Apple Reminders synchronization tools for the dedicated `Baiamonte` and `Baiamonte Treatments` lists.
- Merges duplicate source items by stable source ID first and normalized title second, preserving every source link and returning duplicate Apple IDs for safe completion instead of deletion.
- Adds dated work, planned treatments, projected harvests, recorded contractor attendance, open issue deadlines, Italian holidays, and Google Calendar events to one deduplicated operational calendar.
- Keeps treatment reminder completion separate from agronomist approval and from an applied-treatment record.
