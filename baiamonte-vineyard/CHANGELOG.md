# Changelog

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
