# Changelog

## 1.6.48

- Adds a durable local cistern level model that runs in shadow beside the existing Camera AI estimate without taking control prematurely.
- Backfills every eligible historical cistern observation with strict chronological walk-forward predictions that never use future readings.
- Creates each new live prediction before the next Camera AI result exists, then scores it only when that later result is accepted.
- Reports all-data, historical-backfill and new-live mean error, agreement within five percentage points, maximum error and last-value baseline evidence.
- Keeps Camera AI authoritative until the shadow model has sufficient historical cases, prospective live cases, distinct levels, observed changes and live changes, as well as the required error and agreement scores.
- Treats low-confidence evidence, duplicates and large refill or regime-change jumps as explicit data-quality evidence rather than silently improving the score.
- Shows Camera AI and learned-shadow levels side by side in Today, the cistern detail view, WhatsApp and Admin -> AI.
- Backfills automatically after migration on the first startup and continues learning after every newly accepted camera result.

## 1.6.47

- Sends both readable text and matching audio for Manager choices 1 through 7, 10 and 11: Today, Weather, Work, Disease, Harvest, Cellar/Labs, Cistern, Power and Etna/traffic.
- Keeps Cameras and Team Presence in their appropriate existing formats instead of adding unnecessary duplicate audio.
- Personalizes these high-value live summaries with the person's saved first name, language and individual voice.
- Adds natural topic-specific introductions while preserving the deterministic live evidence and human-readable date, time and weather formatting.
- Retains text delivery if voice synthesis is temporarily unavailable.

## 1.6.46

- Makes the Admin WhatsApp address book authoritative for assistant access, so a saved Reception, Reporter or Manager no longer remains blocked by the legacy environment allowlist.
- Keeps unknown and AI-disabled contacts quarantined while allowing explicitly assigned people such as Wendy to use their saved role immediately.
- Recognizes the approved invitation replies `START` and `INIZIA` as deterministic local menu commands instead of sending them through the AI fallback.
- Adds a per-person keep-alive/reopen action to Admin -> People, automatically using the existing approved no-variable Baiamonte invitation template.
- Shows whether the 24-hour conversation is open and explains that the person must reply to renew it; an outbound template alone is never presented as extending Meta's conversation window.

## 1.6.45

- Recognizes `+` as the global WhatsApp menu command even when no guided form is active, preventing it from falling through to the general assistant.
- Moves every numbered Manager and Reporter information choice onto deterministic live database and Home Assistant snapshots, so ordinary IVR navigation continues working when the AI service is unavailable.
- Adds direct Today/urgent-alerts, Cellar/Labs and Cameras responses and routes Reception weather and harvest choices through verified public snapshots.
- Makes the `*` Back, `+` Menu and `=` Cancel controls consistent across Manager, Reporter, guided-form, invalid-choice and fallback messages.
- Routes common spoken topics such as weather, work, disease, harvest, cellar, cameras and power locally, with natural high-quality summaries; AI remains available for genuinely open-ended interpretation instead of being required for basic facts.
- Adds a database-backed public estate-and-wines response and deterministic media-submission guidance for Reception.
- Adds conservative durable IVR learning: each worker can explicitly choose SAME to reuse the last successfully saved location for that form, while route coverage and AI fallthrough are measured for the Admin monitor without retaining message content.
- Adds a private IVR profile to every Admin -> People card with linked access, language and reply configuration, 30-day routing and completion statistics, and automatic per-person workflow learning from successfully saved forms.
- Lets administrators set the repeated-history threshold for learned locations; the worker must still explicitly confirm SAME, and disabled or retired locations are never silently selected.
- Personalizes each linked person's IVR independently: the menu highlights that person's most-used permitted local choices, while saved-location learning remains isolated by sender and form type.
- Consolidates all person-specific IVR controls in Admin -> People -> Person, including number, access, language, reply medium, individual voice, personalized shortcuts, automatic learning, learned-location confidence and optional AI fallback.
- Defaults replies to the incoming medium so text receives text and voice receives voice; sending both formats requires an explicit per-person selection.
- Normalizes legacy contacts that previously received both formats to Match mode until an administrator or the user explicitly chooses Both again.

## 1.6.44

- Formats WhatsApp dates, times, forecasts and operational responses in natural language instead of exposing database timestamps, machine condition codes or internal timezone names.
- Repairs guided-form Back navigation so the first question returns to record selection and later questions move back exactly one step without retaining the replaced answer.
- Adds a first-class Entire estate choice for scouting, treatment reports and completed vineyard work; whole-estate scouting is stored with authoritative estate scope rather than a misleading block assignment.
- Shortens vineyard choices to field-friendly variety, vine-age and block-code labels and explicitly supports spoken or typed numbered answers.
- Adds fast field controls: `*` Back, `+` Menu and `=` Cancel, while retaining the existing word commands for text and voice use.

## 1.6.43

- Makes the Admin Ministry-catalog process use its recorded integration identity so successful manual and scheduled runs finish as healthy instead of remaining at "Not run yet."
- Runs power continuity monitoring independently from slow integration work so a long Ministry import cannot create a false heartbeat gap.
- Suppresses add-on, Core and host restart gaps as power-outage alerts, clears unconfirmed prior conditions at startup, and retains the restart gap only in the audit trail.
- Changes recovery wording to state that utility loss is unconfirmed unless direct power evidence is available.

## 1.6.42

- Uses small transactional Ministry-catalog write batches so the full official JSON audit record imports within the live Home Assistant MariaDB per-query timeout.
- Reports zero rather than an unknown count before the first successful official-catalog synchronization.

## 1.6.41

- Adds the official Italian Ministry plant-protection product catalog as a weekly, manually refreshable regulatory source.
- Overlays exact registration and reviewable name matches on Baiamonte products; trusted revoked, suspended or expired products are blocked from projected treatments.
- Allows an Agronomist to add a product outside the estate's historical use pattern only after recording its current crop, target, dose limits, PHI, REI and authorized label source.
- Marks products without completed Baiamonte applications as low-confidence first-use candidates and requires Agronomist approval plus paired pre/post-treatment scouting.
- Adds an Agronomy treatment panel for official catalog search, local overlay review, product adoption and crop-use authorization without treating national registration as a label direction.

## 1.6.40

- Expands the owner system manual with the complete authoritative release history from 1.6.0 through 1.6.40.
- Generates the release appendix directly from the project changelog so maintenance fixes and smaller workflow changes are retained in the durable operator record.
- Rebuilds the downloadable PDF and all 36 in-window preview pages with synchronized release metadata and navigation.

## 1.6.39

- Updates the full owner manual through the current Agronomy, Enology, Laboratory, Admin AI, Gmail-cache and guided WhatsApp workflows.
- Documents the weather-first disease model, Agronomist review, paired scouting, learning gates, one-pass two-batch treatment process and young-vine TerraPlus boundary.
- Rebuilds the downloadable PDF and every in-window manual preview page with current release metadata.

## 1.6.38

- Starts the dashboard only after every Agronomy and Enology feature renderer is registered, eliminating intermittent cold-load failures.
- Preserves the active Agronomy or Enology workspace immediately while changing vintages instead of temporarily resetting navigation to Operations.
- Normalizes authoritative laboratory aliases and vintage suffixes during source auditing and corrects four source-confirmed historical sample types.
- Constrains laboratory endpoint and AI-assisted projections to physically possible nonnegative values while retaining the measured adjustment as evidence.
- Guards the embedded weather-map observer against an unavailable document root during iframe startup.

## 1.6.37

- Corrects the worker portal task queue to use the current planned/in-progress statuses and normal priority, restoring assigned work visibility.
- Makes guided WhatsApp issue priorities compatible with the Operations schema and adds the missing lot/tank reference to cellar-operation submissions.
- Expires abandoned WhatsApp forms and calculators after 24 hours, and makes MENU reliably close either workflow before returning to the main profile menu.
- Updates FastAPI, Starlette, the multipart parser and MCP runtime to secure compatible releases after dependency auditing; the resulting environment reports no known vulnerabilities.

## 1.6.36

- Replaces the partial WhatsApp intake menu with complete bilingual guided workflows for Agronomy/Field, Operations and Enology/Cellar records.
- Adds saveable field scouting, phenology, planned treatment reports, completed work, labor hours, issues/tasks, equipment service, fruit maturity, fermentation checks and cellar operations.
- Makes WhatsApp voice notes first-class form answers; complicated reports can be spoken once, reviewed as a transcript summary and explicitly saved into the Operations review queue.
- Adds consistent BACK, CANCEL, MENU, RECORD/REGISTRA and final SAVE recovery paths so active sessions do not strand workers or silently create records.
- Keeps treatment field reports planned and unapproved until the Agronomist completes the legal, safety, weather and product review.
- Adds Admin WhatsApp IVR health, active/stalled session counts, 24-hour completions, voice readiness, workflow coverage and worker command guidance.

## 1.6.35

- Adds durable disease-onset forecasts that project when weather-driven pressure may cross the actionable threshold, with walk-forward validation and explicit confidence.
- Learns treatment effectiveness, observed duration and retreatment cadence from paired pre/post scouting by disease, mixture, dose, block and weather without treating reconstructed pressure as proof of causation.
- Adds chronological active-ingredient and FRAC-group rotation review, blocking repeated groups for Agronomist review when the current product records support the comparison.
- Adds young-vine TerraPlus learning from mapped applications, growth scouting, soil and tissue evidence while retaining the documented-need and Agronomist-approval gates.
- Adds adaptive sensor, duplicate-observation and unreliable-label detection to operational data quality and Admin → AI.
- Adds bounded block-specific disease calibration from parcel/map context, canopy/training system, elevation/aspect, variety and localized scouting.
- Adds outcome-conditioned spray-window learning from wind, temperature, carrier coverage and rain in the first 48 hours after application; legal label and Agronomist limits remain authoritative.
- Rebuilds all connected learning manifests after treatment, scouting and Agronomist review, exposes them in Admin → AI, and provides an administrator rebuild endpoint.

## 1.6.34

- Adds a durable disease-pressure calibration model trained only from explicit Agronomist decisions and comparable field scouting while retaining the weather/phenology rules score as an auditable baseline.
- Applies bounded, small-sample-shrunk disease adjustments to current pressure, Treatments, alerts, WhatsApp and AI consumers; sparse feedback can never move a score by more than 20 points.
- Adds corrected risk scores to the Agronomist review workflow and automatically rebuilds disease learning after reviews, scouting, startup and scheduled pressure refreshes.
- Adds leave-one-case-out calibration error, training-label provenance, season coverage and validation gates to Admin → AI; validation requires at least eight labels across two seasons and performance no worse than the rules baseline.

## 1.6.33

- Adds an audited Agronomist review workflow to current disease-pressure assessments; rejected findings stop driving treatment predictions, while materially changed scores return to pending review.
- Adds treatment-linked before/after scouting with strict block, date-window and disease-marker checks, plus conservative automatic pairing only when one treatment match is unambiguous.
- Rebuilds treatment outcome learning and Admin → AI evidence metrics immediately after paired scouting, while retaining weather as context rather than proof of effectiveness.
- Adds a Treatments follow-up panel for missing baselines, due or overdue post-treatment checks, completed pairs and observed outcomes.
- Caches Gmail folders and message summaries in MariaDB during scheduled intake so Email opens from local data; explicit receive and refresh controls still perform live Gmail checks.

## 1.6.32

- Adds a dedicated **Admin → AI** console containing OpenAI service and credit status, effort and speed controls, budget and projected cost, feature usage, model pricing, and durable-learning health.
- Monitors Laboratory, Agronomist treatment, Harvest, and disease-pressure intelligence with explicit model versions, evidence coverage, data freshness, validation methods, accuracy or error metrics, readiness thresholds, and review-gate warnings.
- Distinguishes measured held-out accuracy from deterministic rules: disease pressure reports Agronomist review coverage without claiming outcome-trained accuracy, and an unavailable model cannot hide the other learning processes.
- Keeps Operations Control focused on system operations and limits the Audit Trail viewport to the latest six visible activities while retaining the latest 100 entries in a scrollable list.

## 1.6.31

- Keeps the durable Laboratory model in an explicit learning-active, low-accuracy state when historical walk-forward direction accuracy is below 60%, even when case and vintage coverage thresholds are met.
- Runs both Laboratory and Treatment durable-learning backfills during application startup so newly installed migrations and historical evidence are reflected immediately in their current pipelines.

## 1.6.30

- Adds durable vineyard-treatment learning with pre-treatment weather, leaf wetness, solar, phenology, scouting, objectives and treatment cadence; 14-day post-treatment evidence windows are cut off before the next application.
- Separates weather-reconstructed pressure from field-observed effectiveness, versions the treatment model and feature schema, calibrates similarity from the 2023–2026 GW2000 history, and keeps the model provisional until adequate seasons and comparable scouting outcomes exist.
- Normalizes historical laboratory identities while retaining every original report label; Nerello, Narello and Nerello/Narello Macalase resolve to the canonical Nerello Mascalese series, alongside documented Grecanico and Grenache aliases.
- Adds durable laboratory cutoff cases, leakage-safe historical walk-forward outcomes, versioned model manifests, per-analyte-and-unit error metrics, and automatic rebuilding at startup and after every new, corrected or reviewed laboratory result.
- Exposes transparent Laboratory and Treatment learning status in their current pipelines and APIs without converting predictions into automatic agronomy, cellar, harvest or enology approvals.

## 1.6.29

- Passes the latest GW2000 disease-pressure snapshot into current treatment simulations so weather-pattern similarity is calculated rather than left unavailable.
- Learns the authoritative product/date/water program from every structured completed treatment, including safety-restricted Treatment 5, while continuing to prohibit historical safety evidence from authorizing a current prescription.

## 1.6.28

- Narrows TERRAPLUS SOLUB NPK 8-7-6 to the small, young vines only and labels its procurement card accordingly.
- Removes TERRAPLUS from general mature-vine, olive and whole-estate nutrition baselines; it remains unavailable unless mapped young vines have a documented need and an Agronomist-directed root-zone or fertigation plan.

## 1.6.27

- Corrects TERRAPLUS SOLUB NPK 8-7-6 from broadcast land/soil fertilizer to vineyard root nutrition for fertigation or localized root-zone application.
- Separates land/soil fertilizer procurement from vine root-nutrition procurement so TERRAPLUS appears with vine nutrition without being mislabeled as a foliar canopy spray.

## 1.6.26

- Rebuilds vineyard treatment simulation around the Agronomist's complete Treatments 2–5 rather than selecting isolated products, while retaining current label, necessity, exact-mixture, weather, PHI/REI, PPE, inventory and Agronomist approval gates.
- Calculates every weather-matched historical program for the current Baiamonte process: one vineyard pass using 400 L total carrier prepared as two identical 200 L batches.
- Makes GW2000 weather the explicit treatment rationale by comparing temperature, humidity, 72-hour and seven-day rain, soil moisture and other available markers with the weather preceding completed treatments.
- Adds continuous, leakage-safe learning: each confirmed completed vineyard treatment stores only the seven days of weather available before application, reconstructed disease pressure, the full recipe and a stable program signature.
- Uses the learned weather match in both live next-treatment review predictions and the simulator, with transparent similarity, model-version, training-case and leave-one-treatment-out validation evidence.
- Keeps restricted historical treatments as behavioral learning evidence only; they never become current reusable prescriptions without fresh safety and authorization review.

## 1.6.25

- Rebuilds the Agronomy treatment simulator around the Baiamonte field process: one complete vineyard pass using 400 L total carrier prepared as two identical 200 L batches.
- Leads with a readable full-treatment recipe showing each necessary product, the amount in each 200 L batch, the whole-treatment amount, inventory readiness, and the current evidence supporting its inclusion.
- Prevents inventory and prior use alone from promoting support, adjuvant, or nutrition products; those products require documented current stress or another explicit evidence-supported need.
- Screens independently significant same-date disease pressure for additional necessary control while retaining exact-mixture compatibility, label, weather, safety, and Agronomist approval gates.
- Adds Laboratory variety-standard cards that show recorded approved analyte markers by variety, sample type, stage, and unit, while clearly leaving missing standards unconfigured.

## 1.6.24

- Removes the red Live cellar records readiness banner from the Cellar page; real tank alerts remain visible, while the informational Demo-mode banner is retained only when Demo mode is active.
- Preserves user-selected values systemwide when live refreshes rebuild a select box's options, including the Laboratory Sample and Measurement selectors, without restoring values that are no longer valid choices.

## 1.6.23

- Preserves the former shared Live/Sandbox choice on the first upgrade to independent US and Italian PayPal selectors, even when Home Assistant pre-populates the new fields with schema defaults.
- Records the one-time migration in persistent add-on data so later operator changes to either account remain independent and are never overwritten on restart.

## 1.6.22

- Adds independent Live/Sandbox selectors for the US and Italian PayPal Business accounts in protected Home Assistant configuration.
- Uses the selected environment for each account's OAuth token, order creation, capture, checkout label, and status light, preventing one account's mode from changing the other.
- Keeps the former shared PayPal environment as a migration fallback for existing installations.
- Makes guest-inquiry deletion persistent by retaining an invisible tombstone linked to the Gmail intake item, so dashboard refreshes and later Gmail checks cannot recreate a deleted inquiry.
- Keeps Labels & dedicated displays selected after saving a tablet assignment instead of returning to the Cellar overview.
- Adds live Online/Offline heartbeat lights to each manually registered cellar tablet, including Tablet 1 and Tablet 2.
- Keeps Laboratory sample and measurement selectors useful when the selected vintage has no numeric report by clearly showing the latest available vintage, while refusing to imply that historical evidence is a current-year measurement or projection.

## 1.6.21

- Exports the protected US and Italian PayPal client IDs, client secrets, and environment from Home Assistant app options into the Register API process.
- Restores the already-configured US PayPal Business account in checkout while preserving the existing EUR-to-US-account fallback when no Italian account is configured.
- Preserves the explicitly selected PayPal environment from protected Home Assistant options; the Baiamonte installation is configured for live PayPal after deployment.
- Adds persistent US and Italian PayPal Business status lights to the sale page, showing Active/Offline and LIVE/SANDBOX before checkout.
- Compacts the oversized Register header pill to a short FIC, PayPal-account, and environment summary; the detailed sync timestamp remains in Integration status.
- Moves Register category buttons to a dedicated wrapping row so Wine, Oil, Hospitality, and later categories are never clipped by the search field or Manual item button.

## 1.6.20

- Routes clear guest tasting, visit, tour, dinner, and reservation inquiries into Hospitality even when the Gmail label or configured subject phrase is missing; the messages remain review-only until explicitly converted.
- Rechecks previously downloaded Gmail message bodies so the existing “Inquiry about Classic Tasting at the Estate” request can enter Guest inquiries.
- Restores saved Atlas parcel and block shapes with an SVG overlay that remains correctly sized when Agronomy is opened after page startup.
- Separates saved boundary counts from parcel center locations so Atlas no longer reports point-only records as verified boundaries.
- Keeps the active workspace, page, and subpage selected when changing years instead of returning the navigation to Operations.
- Suppresses cellar monitor alerts for tanks whose recorded volume is zero; readings remain visible, and guard checks resume automatically when a positive volume is recorded.
- Makes every Finance summary metric clickable and keyboard accessible, opening the selected year’s supporting invoices, monthly result calculation, cash accounts, or individual approved labor and payment records.

## 1.6.19

- Added transparent AI-assisted Laboratory projections: exact prior-vintage evidence is preferred, with a low-confidence 14-day current measured trajectory only when at least two dated readings exist; every refresh and new lab arrival recalculates the outlook.
- Added newest-report AI-assisted finding cards to Laboratory and Vineyard fertilization, with source/review limitations and no automatic cellar, harvest, product, rate, or application decision.
- Restricted Fertilizer procurement to explicitly classified land/soil products; foliar vine-treatment fertilizers remain in Treatments and Crop nutrition.
- Added a dedicated Email tab beside Messaging in Administration, containing mailbox folders, reading/actions, attachments, received/sent history, connection controls, intake refresh, and compose.
- Splits the oversized Laboratory series menu into Sample and Measurement selectors.
- Keeps samples with comparable prior-vintage evidence first while retaining clearly labeled current-only samples.
- Limits the measurement menu to the selected sample, sample type, and stage so unlike records cannot be chosen accidentally.
- Makes “Mark Enologist approved” save immediately and clears the sample’s source-review flag so approved reports stop appearing red.

## 1.6.18

- Opens Laboratory on a series that actually has comparable prior-vintage evidence instead of defaulting to a current-only measurement.
- Groups the selector into measurements with comparable history and measurements that have only a current reading, so unavailable projections are explicit.
- Replaces the misleading mixed-sample annual-average chart with like-for-like vintage endpoints for the selected wine, sample type, stage, analyte, and unit.
- Replaces the process-wide mixed table with the final measured endpoint for that same sample definition in each available vintage.
- Refreshes report history, decision status, trends, comparisons, and projections immediately after a laboratory result is corrected, then reopens the detail with the saved value.

## 1.6.17

- Consolidates safe laboratory label variants such as Grecanico 25/2025, Bianco–Grecanico, Granache/Grenache, and Nerello/Nerello Mascalese for vintage comparison.
- Keeps unrelated wines, sample types, process stages, analytes, and units separate so projections do not combine unlike measurements.
- Adds sample type and process stage to the Laboratory selector, removing visually duplicated choices and making grape, must, and wine series explicit.
- Adds Giancarlo's source-backed December 2024–November 2025 monthly labor to reconciliation: 988 known hours plus one 15-day attendance record whose hours remain explicitly unknown.
- Applies the owner-confirmed €10/hour rate to known historical hours, records all prior labor as paid with ledger entries for the 11 known-value months, and preserves November 2025 as paid with its unknown hours and amount explicit.
- Prevents mirrored source rows from double-counting labor totals and excludes paid historical attendance with an unknown amount from the zero-value invoice warning.

## 1.6.16

- Keeps the active Enology, Laboratory, Bottling, Fertilization, or Nutrition page selected while changing vintages.
- Orders vintage-specific refreshes after the shared year state changes and ignores stale responses from rapid year switching.
- Repairs the Laboratory outlook endpoint under Home Assistant ingress so recorded vintage measurements and projections load instead of an empty fallback.
- Reloads analyte comparisons on every vintage change and exposes the existing source-backed 2023–2025 bottle-equivalent backfill in Bottling.

## 1.6.15

- Defers direct-route activation until the signed-in workspace permissions are available, restoring Laboratory and Messaging links.
- Safely binds the later-loaded laboratory outlook renderer so opening Labs cannot interrupt the page.
- Preserves the Tank Details workspace-save repair and verified Etna status from the previous patches.

## 1.6.14

- Completes the workspace startup repair by safely binding the later-loaded cellar-history renderer.
- Restores the remaining Agronomy, Etna, Laboratory, and Messaging initialization path exposed during live 1.6.13 verification.

## 1.6.13

- Repairs Admin Messaging when Review has already loaded the shared communications data.
- Rebuilds the Messaging panel placement and restores its Contacts, Meta Business, and System-account tab state whenever the page opens.
- Prevents the later-loaded analytics bundle from stopping dashboard startup before Agronomy/Etna, Laboratory navigation, and Messaging are initialized.
- Keeps Tank Details and other Agronomy saves in the current workspace and page instead of returning to Today.
- Keeps direct navigation and cached communications responsive without requiring a full dashboard reload.
- Adds regression coverage for Messaging page activation and stale-panel recovery.
- Leaves the full-version manual unchanged because this is an operational patch release.

## 1.6.12

- Isolates Messaging, Social, and TV browser startup so an error in one page cannot prevent the other pages from loading.
- Adds an independent page-loader fallback for direct navigation and restored sessions.
- Keeps hospitality Gmail inquiry refreshes active while restoring access to the shared Messaging interface.
- Adds regression coverage for page startup isolation and hospitality inquiry synchronization.
- Leaves the full-version manual unchanged because this is an operational patch release.

## 1.6.11

- Aligns the Admin Docs card with the installed owner’s manual release 1.6.4 instead of the obsolete 1.5.0 label.
- Updates regression coverage so the displayed manual release cannot silently drift again.
- Leaves the full-version manual unchanged because this is an operational patch release.

## 1.6.10

- Routes Gmail messages tagged with the configured Hospitality label into Guest Inquiries, including nested labels and messages that were downloaded before the label was applied.
- Retains subject-based hospitality routing as a fallback and exposes configurable inbound labels and subjects in Hospitality Admin.
- Adds a manual Gmail refresh action and regression coverage for label normalization, re-routing, and source metadata.
- Leaves the full-version manual unchanged because this is an operational patch release.

## 1.6.9

- Records harvest picks from multiple vineyard blocks while preserving every legal parcel in the grape-to-tank traceability chain.
- Treats the entered crate weight as net kilograms per crate, calculates the field total, and supports a later authoritative winery weight without erasing the original field measurement.
- Keeps the complete harvest form visible on phones and separates harvest routes from the main application module for easier maintenance.
- Restores laboratory outlooks when switching years by using each report's authoritative vintage and keeps current-vintage projections separate from historical comparisons.
- Resolves Today greetings through the linked Home Assistant person or worker identity while excluding tablet, kiosk, iPad, and service accounts.
- Adds product images to register items and a fast editable manual-charge item while preserving local ledger and inventory behavior.
- Adds regression coverage for harvest weighing and multiple blocks, parcel traceability, laboratory year selection, register behavior, and greeting privacy.
- Leaves the full-version manual unchanged because this is an operational patch release.

## 1.6.7

- Prevents overlapping System Documentation refreshes from leaving the control stuck on “Loading…”.
- Adds a Rome-time greeting on Today and includes a first name only when Home Assistant supplies a natural full human name.
- Shows continuously updated application uptime in Admin Control.
- Adds live Up/Down heartbeat badges for active tank-label tablets based on their latest check-in.
- Adds regression coverage for greeting privacy, documentation refresh recovery, uptime, and label-device status.
- Leaves the full-version manual unchanged because this is an operational reliability patch release.

## 1.6.6

- Keeps every TV card and both sides of split layouts visible on narrower or overscanned displays.
- Replaces unsupported relational CSS selectors with explicit compatibility classes for older Samsung and embedded TV browsers.
- Loads vessel rendering before the main TV bundle and reduces continuous chart and overflow work for smoother long-running displays.
- Adds regression coverage for TV layout preservation, legacy-browser CSS, helper order, and refresh throttling.
- Leaves the full-version manual unchanged because this is a TV reliability patch release.

## 1.6.5

- Reuses healthy MariaDB connections through a bounded, thread-safe pool instead of reconnecting for every small dashboard query.
- Compresses large API and TV-display responses for substantially lower tablet and kiosk network transfer.
- Preserves the existing short-lived TV payload cache while making cold refreshes and concurrent displays more efficient.
- Leaves the full-version manual unchanged because this is a performance patch release.

## 1.6.4

- Adds a complete hospitality partner directory with referral attribution, configurable commission rules, due and approval states, partial payments, payment history, and auditable corrections.
- Connects partner liabilities to the Finance payable total and provides a dedicated partner payment queue and annual summary.
- Expands the System Manual to 24 portrait pages with intelligence-pipeline descriptions, decision trees, evidence gates, partner workflows, and current operational guidance.
- Rebuilds the downloadable PDF and in-window page previews for the updated manual.

## 1.6.3

- Adds Home Assistant-managed network receipt printing through a configured `notify`, `script`, or `shell_command` service.
- Lets administrators select browser printing or the Home Assistant IP-printer path and optionally provide a target printer entity.
- Preserves the existing browser receipt as an automatic fallback when the Home Assistant printer service is unavailable.
- Keeps receipt print counts and audit history consistent for both printer paths.
- Leaves the full-version manual unchanged for this patch release.

## 1.6.2

- Adds an explicit touch-friendly cash-received confirmation with amount due, cash tendered, and change retained in the audit trail.
- Allows administrators to correct payment metadata or void a local payment while preserving its audit history and automatically restoring unposted inventory.
- Protects captured online PayPal payments from local deletion and directs refunds through PayPal before ledger reconciliation.
- Replaces register payment browser prompts with purpose-built tablet dialogs, clarifies the operator-confirmed PayPal phone workflow, and keeps online PayPal API verification separate.
- Refreshes the ECB EUR/USD reference rate once daily while keeping the checkout rate editable and preserving the applied rate on every sale.
- Compacts register item cards and administration controls, and standardizes register buttons for clearer touch targets and states.
- Leaves the full-version manual unchanged for this patch release.

## 1.6.1

- Corrects Giancarlo Pafumi's paid €20 gas reimbursement from the erroneous future date 27 August 2026 to the source-supported date 27 July 2026.
- Repairs the archived July timesheet source alongside the labor ledger and records both before/after values in the audit log without changing the amount or paid status.
- Corrects the archived source title from Mattia to Giancarlo and leaves the full-version manual unchanged.

## 1.6.0

- Adds a tablet-oriented Register workspace with Sale, Inventory, Ledger, and Admin pages plus dedicated Register and Cashier access.
- Mirrors sellable Fatture in Cloud products and prices read-only, includes local Hospitality packages, and supports authorized manual items, editable prices, and discounts.
- Keeps EUR as the authoritative reporting and VAT base while allowing EUR or USD collection at the saved checkout conversion rate.
- Supports both Italian and US PayPal Business credentials, shows the active account at checkout, and preserves the selected account on each transaction.
- Adds an English/Italian checkout switch that controls PayPal locale and the printed receipt language.
- Supports hosted PayPal/card checkout and operator-confirmed PayPal Tap to Pay on an NFC phone without storing raw card data or claiming browser-side POS verification.
- Preserves EUR base values, collected currency and amount, conversion rate, PayPal account, language, and payment reference in receipts and monthly CSV exports.
- Keeps register sales posting to Fatture in Cloud disabled until a separately approved reconciliation release.
- Updates and visually verifies the portrait, scrollable System Manual for the full 1.6 release.

## 1.5.30

- Resolves the seven completed-treatment safety review cases as restricted historical records after exhausting the existing application sheets, product evidence, inventory reconciliation, and owner confirmations.
- Preserves every unknown contemporaneous check and explicitly prohibits these records from being reused as prescriptions; no PHI, approval, calibration, PPE, weather, or compatibility evidence is invented.
- Separates closed historical restrictions from the active safety-information queue while keeping the limitations visible on each treatment card and in administrator data quality.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.29

- Completes a full application, database, pipeline, endpoint, and live-system integrity audit.
- Prevents current inventory balances from creating or reopening shortages in historical treatment years and closes the erroneous 2025 shortage.
- Corrects the fermentation-vessel planning issue that was mislabeled as sprayer equipment.
- Reconciles paid labor timestamps with the authoritative payment ledger so paid invoices and the payroll audit agree.
- Splits chart and historical rendering into a dedicated analytics asset, restoring the browser bundle safety margin without changing the interface.
- Rebinds release tests to the domain modules that now own laboratory, prediction, cellar, and historical behavior.
- Leaves genuine source-review items visible: missing laboratory review, treatment safety evidence, and the known future-dated labor record are not guessed or silently cleared.

## 1.5.28

- Makes Total payable the combined current-year liability: open Fatture supplier balances plus approved outstanding payroll, with both parts shown on the card.
- Adds Net open position as current-year receivables less current-year supplier and payroll payables.

## 1.5.27

- Keeps the prominent totals aligned with the selected finance year because older mirrored invoices do not all contain authoritative historical settlement states.

## 1.5.26

- Adds prominent total receivable and total payable cards to the top of Finance.
- Calculates both cards from genuinely open Fatture in Cloud invoices for the selected finance year.

## 1.5.25

- Applies the EUR 12 default specifically to finished wine bottles, recalculates their total stock value, and preserves the existing unit value of bottled olive oil.

## 1.5.24

- Adds editable finished-bottle stock value with an owner-set EUR 12 per-bottle default and recalculated inventory value.
- Merges approved labor cost, recorded labor payments, and labor due into the main Finance statistics.
- Separates mirrored sales invoices, purchase invoices, and DDT into distinct accounting-document lists.

## 1.5.23

- Treats automatically settled Nexi card-processing fees as paid expenses rather than supplier balances awaiting a separate payment.
- Keeps the fees in the selected-year Fatture expense totals and chart while leaving Gambino Sonia EUR 302.48 as the sole current FIC payable.

## 1.5.22

- Makes Fatture in Cloud payment installments authoritative for exact remaining supplier and customer balances, including partially paid invoices.
- Limits receivables, payables, and accounting lists to the selected year and prevents paid documents from reappearing as open.
- Reconciles the owner-confirmed Giancarlo payment history through July 31 so Payroll outstanding reflects only the EUR 440 current payable.
- Adds a dedicated monthly `Spese da Fatture in Cloud` expense chart using selected-year purchase invoices.

## 1.5.21

- Split stable tank details from changing cellar readings with no duplicated visible fields.
- Tank details now edit code, name, capacity, vessel type, material, location, reading mode, and permanent notes.
- Capacity validation prevents reducing a tank below its currently recorded wine volume; tank-code conflicts are reported clearly.

## 1.5.20

- Added ledger-derived paid-this-year and total-due amounts to every Payroll worker card.
- Payment totals preserve partial payments: paid follows payment dates and due is the remaining approved balance for current-year work.

## 1.5.19

- Added selected-year, prior-years, and combined VAT positions to Finance using the mirrored Fatture in Cloud document ledger.
- Added a year-by-year VAT audit trail while keeping unrecorded settlements and external credits visibly outside the calculation.

## 1.5.18

- Corrects the six live January-June `HISTORICAL-GIANCARLO` monthly attendance rows to the owner-confirmed EUR 10/hour rate; the 962 imported hours now total EUR 9,620 before separate expenses.
- Gives each Act now title two compact lines on the TV Work plan so operational text is not prematurely cut off.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.17

- Prevents stale Home Assistant Person or phone-tracker states from asserting that a person is on site in the administrator directory and detail card.
- Selects the freshest linked phone tracker, rejects invalid `0,0` coordinates and reports presence as uncertain until fresh evidence arrives.
- Adds all-in cost and profit/loss per 750 ml bottle to Finance for the selected vintage: Fatture purchases plus labor and any unbilled winemaking, compared with Fatture sales/receivables and divided by that vintage's bottle equivalents.
- Corrects Giancarlo's imported attendance to the owner-confirmed EUR 10/hour rate and uses the same rate by default for future monthly attendance entries.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.16

- Repairs Admin Control, People and Payroll loading when a Home Assistant person has no source attributes instead of failing the complete administrator payload.
- Deduplicates mirrored Fatture financial documents and assigns the two most recent distinct Sonia invoices to the 2025 winemaking actual.
- Retains the compact two-column winemaking and packaging layout introduced in 1.5.15.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.15

- Reconciles all invoices from the vintage's matching winemaker, so Sonia's two invoices combine into the complete 2025 actual instead of showing only the latest document.
- Lists each matched invoice and amount as evidence while preserving Sebastiano's separate 2026 pre-invoice plan.
- Reflows winemaking and packaging inputs into compact two-column cards that stay inside the narrow cost panel, and counts document-backed delivery records in the price summary.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.14

- Attributes winemaking invoices to the matching vintage plan and provider rather than the invoice calendar year, keeping Sonia with vintage 2025 and Sebastiano as the 2026 planned winemaker.
- Rebuilds the annual winemaking card as a compact, responsive layout with explicit vintage, provider, planned cost, actual invoice evidence and attachment controls.
- Removes unrelated messages from the laboratory source audit while retaining explicit lab reports and the merged two-sample January 2026 draft for review.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.13

- Repairs incoming laboratory Review controls and splits legacy merged AI drafts into one approval per physical sample or named wine, with the original source visible throughout review.
- Treats Italian `Annata` as the authoritative wine vintage and maps explicit sample/wine headings to their matching grape variety instead of substituting the report-date year.
- Audits the 26 owner-supplied CI.MA.LAB reports as 58 distinct physical samples, showing missing samples, incomplete result sets, wrong vintages, merged drafts and possible duplicates without guessing blank Annata values.
- Adds annual winemaking-service planning and invoice reconciliation, corrects packaging supplier classification, and carries bottling/cellar planning into Finance.
- Repairs lazy loading for Admin Control, People and Payroll, and turns live treatment-stock shortages into tracked issues that resolve from inventory or can be deferred for the rest of the season.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.12

- Keeps each incoming laboratory report visible beside the AI draft, with inline image/PDF viewing, explicit download, and source reanalysis that separates multiple wines or samples.
- Prevents duplicate report files and duplicate laboratory measurement sets from creating duplicate records; multi-sample reports remain in review until every distinct sample has been handled.
- Makes incoming-review dialogs easier to close with a large sticky close control, bounded scrolling, backdrop closing, and mobile-safe actions.
- Keeps verified Atlas boundaries attached to the Leaflet map while moving or resizing, simplifies Treatment recipe presentation, hides Home Assistant local-only service accounts, rejects stale device locations as presence, and condenses TV administration.
- Splits laboratory routes, intake review, and system-documentation rendering into focused modules to keep the core application within its maintainability limits.
- Leaves the manual unchanged because this is a patch release rather than a full-version release.

## 1.5.11

- Routes uploaded vineyard soil reports through AI extraction with explicit annual pH, organic matter, nitrogen, phosphorus, potassium and EC fields.
- Lets the Fertilization outlook use extracted values immediately as visibly pending Agronomist review while preserving the original laboratory report and never inventing missing values or fertilizer rates.
- Leaves the manual unchanged because this is a patch release rather than the next full manual release.

## 1.5.10

- Reconciles NOVATEC invoice 429 exclusively from live Fatture in Cloud and removes the temporary duplicate fallback receipt.
- Preserves the owner-confirmed whole-vineyard application of all 500 kg on March 5, 2026, so the authoritative receipt and field use net inventory to zero.
- Leaves the manual unchanged because this is a patch release rather than the next full manual release.

## 1.5.8

- Repairs the Nutrition workspace product lookup so grape and olive baselines load their roles, review conditions, authorization state and stock from the correct treatment reference tables.
- Reasserts that Treatment 5 has confirmed product totals but still requires its unknown operator, exact scope and safety details to be resolved.
- Leaves the manual unchanged for this patch release; manual and PDF regeneration remain reserved for full releases.

## 1.5.7

- Adds a dedicated Nutrition tab under Agronomy with separate grape and olive annual baselines, stage objectives, evidence gates, conditional product review, stock visibility, and a direct handoff into Treatments for any application.
- Shows prior harvest seasons as picked and complete instead of leaving historical varieties or nutrition phases looking active.
- Prevents weather-derived disease pressure alone from promoting GEL DI SILICE, REPENTE, RESOLVE, FRONTIERE or another support product into a calculated program; documented stress, visible symptoms or historical replay evidence is required.
- Audits every completed product rate against comparable current database directions and visibly blocks out-of-range evidence, including GEL DI SILICE at 450 ml/100 L versus the recorded 100–300 ml/100 L range.
- Marks Treatment 5's 400 L and six calculated totals as confirmed-use evidence while retaining its unknown operator, scope, label, calibration, PHI and exact-mixture safety gates.

## 1.5.6

- Records the estate-wide hailstorm occurrence authoritatively as the evening of June 26, 2026, while preserving June 27 and later dates as field-report dates.
- Restores Treatment 5 as completed on June 27 with the owner-confirmed 400 L standard vineyard volume, six applied products, exact per-100-L rates, calculated totals, and inventory use.
- Keeps the unknown application time, operator, treated scope, weather, PHI/REI, PPE and mixture-approval evidence visibly pending instead of guessing them.

## 1.5.5

- Attributes support-product explanations to the independently supported concurrent disease when the selected target itself has no verified product.

## 1.5.4

- Connects same-date weather-driven disease pressure, scenario severity, growth stage, seasonal timing, and prior field evidence to one multi-target treatment program.
- Adds a separate disease-control pass only when another disease has its own moderate-or-higher pressure signal and the date and phenology are suitable.
- Continues with a clearly labeled concurrent-disease program when the selected target has no verified product, instead of hiding another independently supported disease signal.
- Adds nutritional or biostimulant review only for documented stress or a preceding Agronomist-established nutrition program during an active growth stage; nutrition is never presented as disease control.
- Keeps unverified product combinations in separate homogeneous passes and includes every selected product in the required-inventory calculation.

## 1.5.3

- Rebuilds historical treatment simulations from recorded phenology, same-date disease screening, weather, and prior treatment cadence before loading the actual field record for comparison.
- Shows a product-by-product independent replay versus actual Agronomist program, explaining same-target alternatives, different-target products, and nutritional/support additions without copying the historical mixture.
- Matches multi-day completed treatments from their documented operation span, not only the database start date.
- Enforces both per-hectare and per-100-L label ranges so low carrier-water assumptions cannot produce an excessive tank concentration.

## 1.5.2

- Combines the selected field-severity scenario with historical weather evidence instead of allowing a low weather-only score to erase moderate or severe observed conditions.
- Restores justified multi-product simulation programs for historical replays while keeping support products in separate homogeneous passes unless exact same-tank compatibility is verified.
- Adds visible treatment-seasonality intelligence using scenario date, growth stage, historical disease-pressure timing, and Baiamonte's same-month treatment history; it can prioritize review but cannot prove disease or authorize an application.

## 1.5.1

- Moves the treatment scenario simulator into its own focused Agronomy tab.
- Repairs historical replays so the selected date remains visible even when daily weather cannot establish a safety-cleared application window.
- Labels completed simulations clearly while preserving weather, label, compatibility, PHI, REI, PPE, and Agronomist approval gates.
- Shows the complete required-inventory plan for every calculated product, including recorded stock, negative receipt-pending balances, exact shortages, and projected post-treatment balances.

## 1.5.0

- Reorganizes the dashboard into Operations, Agronomy, Enology, Hospitality, and Admin workspaces with Treatments under Agronomy and Laboratory under Enology.
- Splits the long cellar workspace into focused overview, tank-record, and label/display task pages while preserving the authoritative records behind every view.
- Makes system-generated damage-chain assessments read-only and replaces the conflicting editable save with an idempotent Agronomist approval of changed recalculations.
- Allows a scouting observation and its attachments to join an existing damage event or open issue so later reports refine one chronological evidence chain.
- Restricts Home Assistant team-presence data in the WhatsApp IVR and free-text manager assistant to contacts explicitly identified as administrators.

## 1.4.75

- Keeps the latest Agronomist-approved damage-chain result authoritative while newer system recalculations wait as explicit replacement proposals.
- Shows the approved final, system proposal, change, and active forecast on every damage-assessment card with a one-step “Approve as new final” action.
- Prevents later AI drafts from silently changing harvest-yield forecasts after a chain has an approved result.

## 1.4.74

- Links the five-minute live weather refresh, canonical daily rainfall, disease-pressure screening, treatment watch alerts, product program, application-window screening, inventory/PHI checks, and Agronomist approval into one visible treatment pipeline.
- Calculates a multi-product program with a primary disease-control product and one evidence-matched support product when justified, including quantities, inventory needs, homogeneous sprayer passes, and explicit same-tank compatibility gates.
- Replays simulations for prior dates from stored daily weather and disease evidence, and shows the actual treatment recorded on that date alongside—but never copied into—the independent result.
- Preserves negative stock balances while delayed invoices are pending and makes every prepared tank's homogeneous-mixture rule explicit.

## 1.4.73

- Repairs treatment-simulator presentation by resetting Safari-restored stale scenario dates to today on first load and showing the actual forecast-selected application day directly in the result.
- Adds release-version detection that reloads an open dashboard when a newer add-on version is installed, and forces JavaScript, CSS, HTML, and manifest assets to revalidate instead of retaining an old simulator renderer.
- Keeps the complete primary mixture, sprayer fill recipe, reviewed support products, alternatives, excluded products, inventory and safety checks visible in every calculated result.

## 1.4.72

- Persists edited Agronomist damage percentages as the authoritative final value when approved and immediately recalculates the event comparison, adjusted yield totals, and visible forecast impact.
- Queues the learned harvest pipeline whenever a quantitative damage value or approval status changes, so downstream harvest projections are refreshed from the authoritative database record.
- Prevents an estate-wide damage assessment from being approved without an explicit final percentage and confirms the recalculation in the interface.

## 1.4.71

- Makes the system yield-loss determination independent of the Agronomist percentage; the Agronomist comparison is review context only and the reviewed/edited approval remains the final authoritative value.
- Starts the independent system timeline at the first report, then shows each later report's revised event-wide estimate, range and point change.

## 1.4.70

- Consolidates hail yield-loss comparison and the active forecast into one event-level progress chain instead of repeating the same prediction on every supporting report.
- Keeps each field report limited to its own attachments, summarizes aggregate AI evidence without repeating every photo, and adds an explicit event re-run control.
- Seeds a new system-assessment approval from that assessment's system estimate rather than an older Agronomist approval, while keeping provisional and approved values visibly separate.
- Expands treatment simulation with complete primary-product details, sprayer fill recipes, reviewed support products, verified alternatives, excluded products, mixing order, inventory needs, and safety blocks.
- Records and displays the event-wide posterior after each follow-up report, including its range and point change from the preceding determination, without compounding losses or copying another report's percentage.

## 1.4.69

- Makes the treatment simulator use the configured primary GS sprayer by default instead of choosing the first active sprayer alphabetically.

## 1.4.68

- Adds the owner-confirmed Blue Bird Carrier 500 H (code 885160) as the separate tracked carrier asset used with the removable primary GS 200 L sprayer group, retaining official engine, transmission, capacity, track, and weight specifications.

## 1.4.67

- Identifies the primary sprayer as the owner-confirmed GS 200 L M2192017.1 group with AR 252 pump, Honda GP160 engine, M2400050 hose-reel assembly, and M2030102.1 six-nozzle T-bar.
- Keeps the brochure's 25 L/min and 30 bar ratings separate from measured field calibration so exact nozzle flow, selected operating pressure, speed, usable fill and carrier rate remain approval-gated.

## 1.4.66

- Makes treatment-review photographs optional while retaining structured scope, counts and measurements as the primary evidence request.
- Restores growth-stage choices in the simulator and adds a direct system yield-loss calculation control to damage cards.
- Adds Home Assistant configuration defaults for sprayer capacity and calibration fields, and seeds the owner-confirmed FUXTEC FX-MSP2.2 as a second 26 L sprayer pending physical calibration.
- Allows reviewed label or safety-sheet intake to create a new treatment product and source-linked evidence record without silently granting crop authorization or prediction eligibility.
- Preserves negative inventory balances when treatment use posts before a delayed purchase invoice, displaying the pending receipt and automatically netting it when received.

## 1.4.65

- Removes grape, wine, olive, and other general inventory records from the product-label analyzer even when an obsolete treatment-profile link exists.
- Correctly classifies OSSICLOR 20 BLU FLOW as a plant-protection product and deactivates erroneous treatment profiles created for crop and finished-product records.

## 1.4.64

- Restricts the product-label analyzer selector to plant-protection products, fertilizers, and products with an established treatment reference, excluding grapes, olives, wine, and other general inventory items.

## 1.4.63

- Corrects the remaining imported Treatment 3 source-text annotation from 2,250 g total to 2,250 ml total so the displayed historical sheet agrees with the structured IMPULSIVE liquid record and reconciled liter inventory movement.

## 1.4.62

- Shows a compact hail-damage evidence chain with the independent system yield-loss estimate, confidence range, Agronomist-approved percentage, active forecast basis, report/photo counts, and change after newer evidence.
- Recalculates the event result from subsequent reports while preserving the original AI estimate separately from the editable Agronomist approval.
- Corrects IMPULSIVE PREMIUM F to a liquid product, repairs historical application units from grams to milliliters, posts completed use in liters, and prohibits density-based conversion until an authoritative density is supplied.
- Adds reviewable AI ingestion for container labels, manufacturer labels, technical sheets, and safety sheets, preserving the source and requiring Agronomist approval before structured product evidence is accepted.
- Adds editable sprayer profiles with nominal and usable tank volumes, nozzle setup, flow, pressure, speed, carrier rate, calibration date, and completeness checks before a profile can be marked verified.

## 1.4.58

- Replaces free-text growth stages and field observations with controlled, mobile-friendly vineyard dropdowns shared by the dashboard, API, and guided WhatsApp forms.
- Routes each scouting result through every applicable audited pipeline: damage assessment, treatment/stress prediction, harvest prediction, or Agronomist review.
- Supports a combined hail-with-mold/rot report so damage percentage, harvest reduction, and treatment-risk review can progress independently without marking any recommendation approved.
- Prevents disease and mold photos from creating yield-damage proposals unless the selected observation explicitly includes a damage route.

## 1.4.57

- Keeps one deterministic active planning link when Google Tasks or Apple Reminders contains repeated source items, while preserving redundant links as inactive audit evidence.
- Deactivates stale Google task mirrors and links on every successful planning sync so repaired duplicates cannot return as an amber data-quality condition.

## 1.4.56

- Logs the exact migration filename and statement number when MariaDB rejects startup DDL, without exposing credentials or record contents.

## 1.4.55

- Stores new scouting scope and AI evidence in a constrained companion table, avoiding all DDL changes to the legacy scouting table and its MariaDB-managed relationships.
- Keeps whole-estate and variety reports compatible with the legacy required block field by using a validated storage-only anchor that is ignored by authoritative scope calculations.

## 1.4.54

- Adds scope columns and indexes without changing or dropping legacy production constraints; whole-estate and variety reports use a validated internal anchor block while their explicit scope remains authoritative.
- Conditionally restores block or variety foreign-key protection only when the database reports that relationship missing after an earlier failed attempt.

## 1.4.53

- Drops the legacy scouting-block foreign key in a separate idempotent MariaDB statement before rebuilding the scouting table, then conditionally restores both block and variety integrity constraints under unique names.

## 1.4.52

- Makes every migration 082 scope column and index idempotent so a MariaDB host can recover safely from a partially attempted DDL change.
- Retains application-level estate ownership validation for optional block and variety scope fields without recreating conflicting foreign-key names during startup.

## 1.4.51

- Uses a distinct name for the replacement optional scouting-block foreign key so MariaDB can apply migration 082 atomically after dropping the original constraint.

## 1.4.50

- Serializes database migrations across the Operations and public-label services with a MariaDB advisory lock, preventing simultaneous startup from attempting the same schema change.

## 1.4.49

- Marks the authoritative 2026 hailstorm event chain as whole-estate while keeping geographic extent separate from assumed damage severity.
- Adds scope-aware AI damage estimates with central, low, and high percentages for reported zones, blocks, varieties, and representative whole-estate surveys.
- Reassesses all current chronological reports and photos as supplementary evidence arrives, records change from the previous AI result, and keeps every result draft-only until Agronomist approval.
- Preserves approved harvest forecasts while a newer assessment is pending and continues to use only the latest approved event evidence without compounding follow-up reports.

## 1.4.48

- Adds calculated scouting and photo-based damage-reduction proposals with confidence, source evidence, mapped block/variety area, and a visible kilogram preview.
- Groups supplementary reports into stable event chains and derives improving, stable, or worsening progress without compounding follow-up estimates.
- Requires Agronomist approval before any proposal changes the authoritative harvest forecast; the latest approved report replaces the prior report for the same event, block, and variety.
- Reconciles approved reductions through Vintage, blend planning, projections, allocations, wine output, and TV displays while isolating every vintage year.

## 1.4.47

- Completes the treatment prescription by calculating every selected ingredient for each physical sprayer fill, not only the total mixture and carrier-water split.
- Shows practical grams or milliliters for sub-unit batch quantities while preserving exact mass and volume totals without unsafe conversions.
- Keeps per-batch recipes subordinate to the existing Agronomist, label, compatibility, PHI, REI, weather, PPE, stock and calibration approval gates.

## 1.4.46

- Adds the approved 2026 hail-event assessment timeline for the June 26 evening event, with its June 27, June 30, and August 6 field-photo evidence.
- Makes the latest approved assessment replace earlier estimates for the same damage event, preventing compounded harvest reductions.
- Adds Agronomy controls to view, edit, approve, or remove damage assessments while preserving the audit record.
- Leaves forecast impact unchanged when an estate-wide loss percentage is not supported, rather than guessing from close-up photos.

## 1.4.45

- Keep active camera tiles refreshing on unattended and secondary-HDMI kiosk windows.

## 1.4.44

- Keep the TV dashboard, camera pages, ADS-B, and AIS data refreshing when Chromium places an unattended or secondary-HDMI window in the background.
- Bypass the browser cache for live TV JSON requests so every refresh uses current Baiamonte data.

## 1.4.43

- Make the reconciled database work plan authoritative for the TV Today page and show only current or future actionable work plus upcoming hospitality.
- Prevent completed or cancelled treatments from reopening when a stale Google Task or Apple Reminder still says it needs action.
- Recognize explicit `COMPLETATO` / `COMPLETED` task titles as closed work and repair existing stale treatment tasks during migration.

## 1.4.42

- Treat the current Home Assistant Person state as authoritative until Home Assistant changes or invalidates it, instead of falsely expiring unchanged presence after 45 minutes.
- Resolve renamed Home Assistant Person entities and their attached trackers for People, manager messaging, and payroll presence checks.
- Keep camera-recognition evidence time-bounded while ensuring People, Payroll, and WhatsApp report the same conservative presence result.
- Move People profile presentation and payroll presence resolution into focused modules to keep the core application within its maintenance budgets.

## 1.4.41

- Restore the shared known-value formatter and projection renderer as true global functions, eliminating the `known is not defined` popup across harvest, cellar, blend, and projection views.
- Add a regression guard that rejects stray patch prefixes in the harvest dashboard extension.

## 1.4.40

- Repair Fatture in Cloud Agriplanet stock ingestion by classifying current and historical receipts before any treatment-stock evidence uses that result.
- Preserve the owner-confirmed zero-stock boundary on 1 January 2026 while allowing both earlier historical supplies and current receipts to sync reliably.

## 1.4.39

- Keep valid payroll-only workers active without requiring a Home Assistant account or Person immediately.
- Add a deferred **Link Home Assistant** workflow that appears only for identified, unlinked payroll workers and preserves all labor, approval, and payment history.
- Validate and audit every administrator-approved payroll-to-Person link, then use the selected Home Assistant name and identity authoritatively on subsequent refreshes.

## 1.4.38

- Keep payroll-card actions attached to the worker's stable identity after sorting by hours, so only genuine unidentified historical workers show **Identify worker**.
- Reconcile hourly and monthly payroll identities with authoritative Home Assistant Person names while retaining prior names as exact history aliases.
- Mark payroll identities explicitly as identified and Home Assistant-linked, preventing UI behavior from being inferred from card position or display text.

## 1.4.37

- Add complete, bilingual WhatsApp guided forms for field scouting, phenology and fruit-maturity samples, using live block and grape choices and an explicit final save step.
- Keep field evidence distinct from treatment and harvest approval, audit every guided submission, and queue harvest-prediction refreshes when new field evidence is saved.
- Expand the WhatsApp operational-submission menu with complete field requirements for labor and services, completed work, harvest receipts, cellar work, treatments, and inventory or finance review.
- Reconcile completed treatment quantities against received stock, retain zero as the visible minimum when historical use exceeds recorded receipts, and improve purchase advice from the reconciled balance.
- Complete current treatment-product directions, use the configured 400 L sprayer basis, and correct Gel di Silice to liquid dosing and inventory units.
- Add reviewable AI photo analysis for scouting, phenology and maturity evidence and apply only bounded, non-authoritative suggestions.
- Adjust production projections from deduplicated, reviewable scouting damage evidence without changing baseline forecast records.

## 1.4.36

- Make vineyard TV alerts cycle through open items and return to the newest alert instead of stopping at the end.
- Replace the generic laboratory suggestion box with a compact enology decision brief showing review state, priority readings, next action, next check, and review queue.
- Keep completed work out of the active TV work plan.
- Compact TV communication, review and delivery-alert rows to titles and timestamps without message-body details.
- Page overflowing Communications and Work Plan lists row by row, preserve unchanged content, and loop reliably on Samsung TVs.

## 1.4.35

- Keep completed tasks out of the active unified work plan and constrain long work-plan, calendar, and issue lists to readable scrolling panels.
- Contain the finance source status inside the same visual system as its other connection indicators.
- Make Today and Review use one clear active-alert meaning, acknowledge live conditions without letting them reappear, and preserve automatic resolution when conditions clear.
- Separate active issues and follow-up from closed history, record terminal dates consistently, clear stale dates when reopening, and stop undated legacy closures from leaking into unrelated years.

## 1.4.34

- Repair OpenAI credit rechecks by using the model's supported minimum output limit and show the provider's actual failure detail when a check cannot succeed.
- Add persistent Low, Medium, and High AI effort controls plus Economy, Standard, and Fast processing choices to Operations Control.
- Apply the selected AI mode to every Responses API text and vision request while keeping Standard and Medium as safe defaults.

## 1.4.33

- Keep the automatic OpenAI credit retry deadline stable while the Admin page refreshes.
- Distinguish available, blocked, unverified, and not-configured API status instead of assuming that no alert means credits are usable.

## 1.4.32

- Enforce January 1, 2023 as the operational-data boundary in dashboard year selection, charts, history feeds, lab trends, cellar and grape summaries, olives, treatment-pressure comparisons, projections, and display payloads.
- Keep rejected pre-operation evidence stored for audit without allowing it to appear in operational dashboards or influence forecasts.
- Show AI cost statistics with two decimal places and distinguish local usage estimates from the provider's prepaid balance.
- Add a direct OpenAI balance link plus a tiny, automatic credit-availability recheck that clears the AI quota alert as soon as a newly funded API request succeeds.
- Remove unreachable database-write code beneath the read-only finance guards; Fatture in Cloud remains authoritative.

## 1.4.31

- Slowly scroll overflowing TV lists on Today, the seven-day plan, latest laboratory guidance, INGV notices, and communications while preserving position across refreshes and pausing inactive screens.
- Remove frontend row caps from those TV panels so every row supplied by the database-backed display feed can become visible.
- Start estate vintage, production, cellar, laboratory, and operating-history charts with Baiamonte's first actual harvest in 2023 while retaining rejected 2022 evidence for audit history.
- Scale TV chart typography, margins, strokes, and pressure trends to remain readable on large high-resolution screens.

## 1.4.30

- Add database-backed olive harvest-style preferences and a confidence-labeled greener-harvest prediction to Olives and Today without using a fixed calendar date.
- Reject the invalid pre-operation 2022 grape harvest record and start operating-history harvest charts with the estate's first actual vintage in 2023.
- Keep Etna, trends, projections, finance summaries and historical operating evidence database-authoritative while removing the retired workbook runtime dependency and image payload.
- Keep financial history private to finance-authorized users and distinguish completed treatment trends from planned records.
- Repair the digital-label logo, compact header and shared physical tank animation, and activate the corrected label assets immediately with release 1.4.30.
- Show every database-backed Today priority notice in severity order, scroll overflowing Today and Intelligence alert lists, and use one authoritative feed for counts, urgent findings and notices.
- Align Today dates and vintage selection with Europe/Rome, and clearly distinguish a historical-vintage review from live estate systems.

## 1.4.29

- Automatically resolve weather, cellar, cistern, disease, laboratory, task, system, power, AI-service and Etna alerts when their underlying condition clears, including matching Home Assistant notifications.
- Expand Today and Weather dashboards with condition, reading freshness, wind and gusts, soil moisture, UV, pressure, solar radiation, dew point, VPD, forecast and active vineyard advice.
- Make database weather fallback retain the complete sensor record and remove the retired weather-file upload path.
- Disable all remaining workbook migration command entry points so MariaDB and authenticated application or connected-service inputs are the only operational authorities.

## 1.4.28

- Make the Projections section clear stale values after a failed refresh and label allocation and outlook ranges from the selected database year.
- Show database forecast provenance and keep Operations and TV scenario ranges aligned with the same historical evidence.
- Retire every workbook write path, remove dormant upload controls, and make MariaDB the sole authority across projections, finance, olive history and operational records.

## 1.4.27

- Confine fermentation bubbles and process motion to the wine inside each physical vessel.
- Remove the stray animated bubble field from the surrounding tank-label card.
- Serve a true transparent-background logo to label tablets instead of relying on kiosk-browser blend modes.

## 1.4.26

- Blend the tank-label logo into the animated background instead of showing its rectangular image canvas.
- Replace the old fermenter silhouette with a visibly new stainless cylindroconical vessel shared by the label and `/tv` views.
- Keep the liquid-level and fermentation motion inside the new physical vessel design.

## 1.4.25

- Replace the legacy tank-label wordmark file with the current official Tenuta Baiamonte logo asset.
- Prevent the larger tank title from overlapping its status line and header divider on compact kiosk screens.
- Preserve the larger legal-field and reading typography introduced in 1.4.24.

## 1.4.24

- Make the Hospitality workspace use the same reliable menu activation path as Operations and Admin.
- Switch Reservations, Guest inquiries and Hospitality Admin correctly on desktop and mobile.
- Restore the last selected Hospitality subsection when returning to the workspace.
- Make always-on tank labels activate new container artwork immediately when a display release is installed.

## 1.4.23

- Generate the Android managed-device provisioning QR inside Vineyard Operations instead of opening Fully Cloud's popup.
- Cache the checksum-pinned official Fully Kiosk Browser EMM installer in the add-on and serve it through the read-only HTTPS label gateway.
- Import a private one-page profile that starts the assigned label automatically after boot, recovers after connection loss and enables local-network Remote Admin.
- Keep a separate Start URL QR as a manual fallback and retain the per-tablet permanent-link QR codes.
- Compact the enology workspace, tablet controls and setup instructions while moving multi-year history and AI review behind clear expandable sections.

## 1.4.22

- Use the same physical container silhouettes and stage-driven liquid motion on digital tank labels as the cellar `/tv` page, enlarged for tablet readability.
- Serve cached label data when the network returns a temporary server error, including the unassigned-tablet screen.
- Require the configured HTTPS label gateway for provisioning so service-worker offline support is available.
- Allow operations users who manage tablets to open their QR codes, and preserve the short-screen vessel layout.
- Synchronize the API release version and extract provisioning routes to keep the main application module within its size guardrail.
- Move the label service startup migration hook to FastAPI's supported lifespan API.
- Add GitHub release checks for dependencies, Python compilation, JavaScript syntax and the complete test suite.
- Lock the WhatsApp service dependency tree and update Express to the patched 4.22.2 release.
- Keep the agronomy dashboard available when no public label gateway is configured, and never use stale cached labels for revoked 404/410 links.

## 1.4.21

- Cache each read-only tank and tablet label shell, branding and last successful data response so an already visited label can reopen during a connection outage.
- Mark saved offline readings with an amber status light and an explicit `Copia offline` notice while keeping enrollment and administration uncached.

## 1.4.20

- Enlarge the Baiamonte mark and increase the compact landscape label typography for easier reading on cellar tablets.
- Make the live vessel more legible with a larger silhouette, layered liquid movement, rising fermentation bubbles and a restrained active-tank glow.

## 1.4.19

- Add an individually generated QR code beside every registered tablet's permanent kiosk link.

## 1.4.18

- Fall back to a selectable copy window when Home Assistant ingress or the device browser blocks direct clipboard access for provisioning and label links.

## 1.4.17

- Show the Fully Kiosk Start URL and its scannable QR code together with one action in the tablet-provisioning panel.

## 1.4.16

- Treat Meta WABA account review as a separate prerequisite from business verification. The live Baiamonte WABA is business-verified but its account review is still pending.
- Disable the PIN and registration controls until both `business_verification_status=VERIFIED` and `account_review_status=APPROVED`, preventing repeated rejected requests while Meta finishes review.

## 1.4.15

- Read Meta's WABA business-verification and account-review states directly from the official Graph API alongside phone ownership and display-name status.
- Block repeated WhatsApp registration attempts while the WABA is unverified, explain the distinct account-level prerequisite, and link administrators to Business Support Home.

## 1.4.14

- Preserve Meta's safe registration diagnostics, including user-facing details and error subcodes, so a rejected WhatsApp Cloud API registration can be corrected instead of appearing only as `(#100) Invalid parameter`.
- Show the verified number's ownership, display-name and platform readiness beside the one-time registration form without exposing the access token or PIN.
- Stop registration early when Meta has explicitly rejected the WhatsApp display name.

## 1.4.13

- Add the missing one-time WhatsApp Cloud API registration control for verified production numbers.
- Send the six-digit registration PIN directly to Meta without retaining it in the dashboard, runtime settings, logs, or database.
- Activate the registered production sender only after Meta confirms `/register` success.

## 1.4.12

- Keep the vineyard atlas at the operator's selected center and zoom through data refreshes, tab changes, rotations, resizing, and page reloads.
- Preserve the selected base map and visible atlas overlays, while retaining explicit Fit land and Baiamonte reset controls.
- Avoid rebuilding the Leaflet map when refreshed atlas data has not changed.

## 1.4.11

- Fix treatment prescription and stock guidance cards to honor the active light/dark theme instead of forcing a white background.

## 1.4.10

- Imports Agriplanet supply history with accurate Fatture in Cloud date filtering, canonical treatment/fertilizer matching, and a zero-stock bridge into the confirmed 2026 baseline.
- Compacts Today and Work Plan TV rows, fixes the planning-row grid, and displays up to eight useful items per section.
- Adds a verified-number WhatsApp Cloud API registration path that never stores or logs the six-digit PIN, then activates the registered production sender.

## 1.4.9

- Add a live Needed stock list to treatment predictions with required, on-hand and shortage quantities.
- Automatically ingest recognized treatment-stock lines from Agriplanet received invoices during the existing Fatture in Cloud sync.
- Reuse invoice and stock records idempotently, keep Fatture in Cloud read-only, and exclude unrelated Agriplanet lines from treatment inventory.
- Treat January 1, 2026 stock as zero and post every 2026 Agriplanet invoice on its actual date; show unfamiliar lines in a classification queue instead of guessing.

## 1.4.8

- Post the supplied 2026 invoice quantities as actual inventory stock receipts with quantities, units, unit costs and source links.
- Show received and current on-hand stock in the treatment prescription, and distinguish in-stock, insufficient-stock and suggested-purchase products.

## 1.4.7

- Replace the stale Treatment 5 plan and copied recipe with an evidence-based, fail-closed prescription proposal.
- Calculate a target-specific mixture by treated area and water volume, show per-hectare, total, and per-100-L quantities, and select only a conservative weather window.
- Keep scouting, exact blocks, water volume, current label, PHI, REI, compatibility, weather, PPE, stock and Agronomist approval as visible application gates.
- Import the two supplied 2026 Agriplanet invoices as purchase evidence, while clearly allowing recommended purchases outside the invoice history.
- Mark Sacron 45 WG unavailable after its recorded 2026-08-15 authorization expiry and prevent invoices or historical use from overriding current legal status.

## 1.4.6

- Render all 17 portrait pages in the scrollable in-window system-manual viewer.

## 1.4.5

- Fix the Agronomy dashboard's internal treatment call so it always requests the vineyard scope after the crop-specific treatment split.

## 1.4.4
- Separate vineyard and olive treatment programs at the database, API, entry-form, prediction, and dashboard layers.
- Restore the 2026 olive treatment from the owner-supplied treatment sheet with exact products, per-100-L doses, 200 L water volume, and calculated product totals; retain legal and safety checks as unconfirmed where the source is silent.
- Import the two historical 2025 olive treatments from exact workbook rows without inventing missing products or doses.
- Repair vineyard treatments 2-4 from the owner-supplied sheets, including their real multi-day operation dates, products, doses, instructions, and the one exact 500 L water total.
- Keep Treatment 1 visibly incomplete and Treatment 5 planned until authoritative evidence changes their states.
- Add an olive harvest-date outlook based only on exact estate harvest dates, with an uncertainty window and explicit confidence.
- Remove the 45-day cutoff that hid old overdue treatment plans and exclude unconfirmed or olive applications from vineyard disease-model recency.
- Add a fail-closed product-selection layer that can rank only current crop-and-target authorizations; historical product use alone never becomes a recommendation.

## 1.3.31
- Keep Home Assistant authoritative for each person's name and username by reconciling ingress user identity at sign-in; Vineyard Operations remains authoritative only for estate role, access and approval responsibilities.
- Remove the temporary Sebastiano name override so Home Assistant People corrections appear directly in the dashboard.

## 1.3.30
- Correct Sebastiano Vinci's dashboard display name while preserving the existing Home Assistant Person link and combined Agronomist & Enologist role.

## 1.3.29
- Rename the Cellar tab to Enology and place tank, wine-lot, cellar-reading, blend, label and display controls in that workspace.
- Give Agronomy a distinct vineyard workspace for scouting, phenology, maturity, harvest readiness and field planning while keeping Treatments as its own dedicated tab.
- Correct treatment and disease-pressure guidance so Agronomist review is required without incorrectly assigning Enology responsibility.
- Add the combined Agronomist & Enologist estate role, assign it to Sebastiano Vinci for the current operation, and enforce discipline-specific approval gates for disease/treatment and lab/cellar decisions.

## 1.3.28
- Make the TV intelligence page consume its actual remaining screen height, allowing disease-pressure charts to shrink correctly on shorter and lower-resolution TV browsers.
- Remove Sebastian's name from TV treatment guidance and use the role-based terms Agronomist and Enologist.

## 1.3.27
- Replace Safari's embedded PDF frame with a portrait, vertically scrolling page viewer that works reliably on tablets and phones.
- Keep the original PDF download available and render all 16 pages sharply inside the administrator Docs window.

## 1.3.26
- Add an administrator-only System Manual in Docs with in-window viewing and PDF download.
- Repair the authoritative 2024 olive seed and estate scoping while showing unsaved years as not modeled instead of a false zero-cost result.
- Refresh hidden Atlas geometry safely, reveal prepared Gmail replies, reclaim stale intake work atomically, and prevent replies to unapproved WhatsApp senders.
- Restore contact filtering in compact messaging views and add regression coverage for the repaired workflows.

## 1.3.25
- Corrected olive YoY history keys and restored the owner-supplied 2024 cost defaults before the first authenticated save.
- Sentinel-2 readiness now recognizes the seven verified cadastral parcel polygons as the estate geometry fallback instead of falsely reporting that the mapped estate has no geometry.

## 1.3.24
- Made olive-cost startup independent of historical estate re-keying by keeping defaults in the dashboard until the first user save writes them with the app's verified live estate identity; database foreign-key protection remains intact.

## 1.3.23
- Corrected the olive cost migration to use the canonical seeded Tenuta Baiamonte estate UUID used throughout the database schema.

## 1.3.22
- Fixed the olive cost migration to resolve the active Tenuta Baiamonte estate by slug, so installations with the canonical live estate ID start reliably.

## 1.3.21

- Record the owner-authoritative 2024 olive result of 332 kg and 40 liters, calculated as 8.3 kg per liter and 12.048% oil yield.
- Add an editable annual olive cost model for pressing, bottle size and count, bottling, supplier net and VAT, annual labor, harvest labor and per-tree harvest rate.
- Calculate costs from the inputs—220 × €2.30 is €506 and €751 + 22% VAT is €916.22—without retaining incorrect handwritten arithmetic.
- Reconcile pressing and bottling as components of the supplier subtotal by default so the invoice is not double-counted; allow switching the invoice to a separate added cost when appropriate.
- Graph euro cost components and actual oil bottle equivalents against the bottle plan, with total, per-liter and per-bottle economics.
- Add dedicated year-over-year charts for harvested olives, oil output, kg-per-liter conversion, total modeled cost and cost per liter.

## 1.3.20

- Keep the live alert and intake queues visible while folding secondary Gmail, upload, AI and processing tools into compact expandable rows.
- Place upload and vineyard-question tools side by side on larger displays and collapse the detailed WhatsApp assistant configuration until needed.
- Arrange alert delivery rules in responsive columns with tighter controls and channel status cards, preserving every routing and safety setting.

## 1.3.19

- Render the Treatments board inside its own failure boundary and redraw it whenever the tab opens, so healthy treatment data cannot be hidden by another dashboard section's drawing error.

## 1.3.18

- Draw the vineyard Atlas only after its page is visible and initialize Leaflet with the Baiamonte estate view, preventing the world-map startup state.
- Keep verified parcel geometry available when the optional official cadastral WMS cannot initialize.
- Isolate Atlas rendering failures from the rest of the dashboard and redraw Alert Settings directly when its page opens.

## 1.3.17

- Protect approved, rejected, and archived intake from delayed or duplicate AI analysis, with atomic processing claims and safe stale-worker recovery.
- Restrict WhatsApp approval and rejection to the Manager role; Reporter submissions remain queued for manager review.
- Quarantine messages from senders outside configured Gmail and WhatsApp allowlists without automated analysis or replies.
- Validate the selected Meta receiver before ingestion and analyze captioned media and selected group evidence reliably.
- Remove intake files when a duplicate or failed database insert rolls back, and count linked-account messages only after accepted ingestion.
- Show six nearest tasks and six genuinely recent completed-work rows, excluding future-dated work from the Recent work card.

## 1.3.16

- Prevent the early-loaded messaging bundle from calling application helpers before they exist, eliminating the startup JavaScript error.
- Bind the grape and cellar history selectors after the main application has initialized so their charts remain interactive.

## 1.3.15

- Restore David Rahamin as the approver on 22 paid July labor rows whose retained source notes explicitly identify his confirmation.
- Classify six zero-value historical attendance rows as non-payable paid records instead of falsely reporting missing payment timestamps.

## 1.3.14

- Derive paid, payable, verification-hold and outstanding payroll totals from the non-voided payment ledger, including deposits and partial balances.
- Surface verification-held labor in a separate administrator queue and require an explicit audited release before payment.
- Protect paid invoices from financial edits or deletion, reject held and zero-value payments, and prevent batch payments from duplicating an existing partial ledger.
- Expand payment integrity diagnostics and add a database constraint that rejects zero or negative payment rows.

## 1.3.13

- Keep the audited harvest-model evidence visible after the later-loaded harvest and blend extension renders, preventing the legacy compact recommendation list from replacing it.

## 1.3.12

- Populate the harvest recommendation dashboard with predicted dates, GDD progress, operational confidence, training vintages, and leave-one-vintage-out back-test error.
- Show the health and strict decision role of the credential-free ensemble, seasonal, SIAS, and Sentinel-2 evidence feeds; visibly flag the missing block geometry needed for satellite trends.
- Prefer the ready learned target over cold-start configured GDD, cap evidence-based AI timing interpretation to three days, and prevent deterministic and ensemble forecasts from double-counting the same future weather.
- Label SIAS as historical-catalog-only and disclose the limited available-year baseline behind seasonal anomaly comparisons.

## 1.3.11

- Tolerate missing ECMWF seasonal member and ensemble-mean values without failing the source refresh.
- Load the external prediction cadence and authorized public-location switches into the running application environment while preserving privacy-off defaults for new installations.

## 1.3.10

- Add credential-free Open-Meteo ECMWF ensemble forecasts with member spread and probability thresholds; any automatic picking-date effect is horizon-limited and capped at one day.
- Add ECMWF seasonal temperature and rainfall outlooks with local observed-climatology anomalies for early planning only; seasonal data is prohibited from selecting an exact harvest date.
- Add a SIAS regional validation connector that visibly reports the anonymous catalog's historical/stale state and never replaces the on-site GW2000.
- Add a privacy-gated, credential-free Sentinel-2 block vegetation connector for NDVI, NDRE and an explicitly labelled LAI estimate; exact block polygons are not transmitted without owner opt-in.
- Store source freshness, failures, roles and evidence snapshots in MariaDB and expose them through the process monitor and prediction-source API.

## 1.3.9

- Require every new grape laboratory report to identify its variety, calculate fresh latest-value and per-day analyte trends, and exclude readings older than 21 days from forecast adjustments.
- Durably invalidate and recalculate harvest predictions within the next one-minute scheduler pass when laboratory, maturity, phenology, scouting, treatment, plan or actual-harvest evidence changes.
- Make MariaDB the sole operational authority by retiring the workbook upload UI and API while preserving previously migrated rows as immutable database provenance.
- Record the database authority, workbook independence, learned-model calibration and lab statistics inside every forecast evidence snapshot.

## 1.3.8

- Normalize every retained Nerello legacy spelling to the authoritative 2023-2025 pick date and evidence status, preventing stale alias metadata from appearing in merged historical views or model inputs.

## 1.3.7

- Keep the learned GDD/calendar ensemble from being blended a second time with the same historical pick-date evidence.
- Prevent narrative AI review from moving a learned harvest date when no current grape laboratory or maturity measurement exists; missing evidence now lowers confidence without inventing a date adjustment.

## 1.3.6

- Apply the user-authoritative nine-date harvest matrix for Grecanico, Grenache and Nerello Mascalese across 2023, 2024 and 2025.
- Clear earlier pick dates from operational history and training while retaining only the correction audit; preserve ancillary pressing evidence without associating it with a discarded pick date.
- Expand learned harvest-date training and backtesting to three complete vintages.

## 1.3.5

- Add the September 17, 2023 Grenache lot as the first pick while retaining September 24 as the later confirmed pick.
- Preserve its crew, crate, mastalone, pressing-pressure, tank 13 and approximate bottle evidence without converting ambiguous wording into invented quantities.
- Add exact 2025 pick dates for Grecanico, Grenache and Nerello Mascalese, expanding learned-model training and two-way vintage backtesting.

## 1.3.4

- Add an auditable small-data harvest learning model that learns standardized GDD-at-pick and variety timing offsets from exact historical harvest records.
- Gate learned dates on at least three exact variety/year records across two vintages, with leave-one-vintage-out backtest error and visible missing-evidence status.
- Standardize the model's historical and current base-10 GDD calculation, select one preferred weather source per day, and preserve expert-confirmed plans.
- Show model training progress or measured backtest error on the vineyard TV instead of presenting seasonal fallback dates as learned predictions.
- Record the user-confirmed 2023 Grecanico, Grenache and Nerello Mascalese pick dates as exact training evidence, with their later crushing dates preserved separately as cellar chronology.

## 1.3.3

- Fix the live harvest-refresh SQL alias used by the new maturity-evidence filter and cover the declared alias in regression tests.

## 1.3.2

- Exclude placeholder maturity rows and unreviewed laboratory results from harvest confidence and recommendation evidence.
- Cap disease-model refreshes at 30 minutes and correct the recent-rain window to the current plus two prior calendar days.
- Keep rainfall-bug model v2 assessments out of current and historical disease views while retaining their database audit trail.
- Label long-range workbook production outlooks as planning projections, including their stored provenance.
- Add behavioral regression coverage for prediction evidence and cadence safeguards.

## 1.3.1

- Apply the audited physical-tank occupancy rule to the TV payload as well as the dashboard and label APIs, preventing planned empty lots from duplicating a vessel on the live display.

## 1.3.0

- Correct disease-pressure rainfall by using canonical daily totals instead of summing repeated cumulative station observations.
- Keep planned zero-volume wine lots from replacing current manual tank contents, duplicating physical vessels, or producing incorrect tank labels.
- Exclude laboratory reports still marked for review from forecast-evidence counts and show the excluded count explicitly.
- Add a compact operational data-quality snapshot for future dates, laboratory vintages, treatment safety, and shared vessel assignments.

## 1.2.45

- Restore the Grape and Projections dashboards by importing the historical vintage reconciliation helper used by both views.
- Close the matching canonical work-plan task whenever a treatment is completed, publish that completion to the shared task source, and reconcile already-completed treatment tasks during migration.
- Collapse repeated audit events for the same treatment action in user-facing processed history while retaining the full database audit trail.
- Reject future-dated reimbursements and keep laboratory samples marked for review out of harvest-model inputs.

## 1.2.40

- Reconcile every selected dashboard year across harvest, work/labor, cellar, olives, laboratory, treatment, weather, finance, issues and historical Apple Notes evidence.
- Include recorded labor rows and hours in the main Work logged metric and recent-work timeline without double-counting separate work-activity hours.
- Surface all historical Apple Notes facts in the selected-year History view, including retained conflicts; show 2023/2024 bottled production in Cellar and olive-source evidence in Olives without promoting disputed values to canonical actuals.
- Keep issues inside the years when they were actually active instead of repeating current 2026 issues throughout 2022–2025.

## 1.2.39

- Represent the source-preserved, unsplit Federico 2023–2024 compensation period in both affected year views without allocating its amount or inventing hours for either year.
- Mark a year as partial labor coverage when exact recorded hours coexist with historical source activities whose hours were never recorded.

## 1.2.38

- Audit prior-year labor and harvest chronology against the Baiamonte workbooks, the canonical audit register, Apple Notes and the live database without converting payment dates or note modification dates into work or harvest dates.
- Show every source-traceable historical activity for the selected year in newest-first order, including its exact-day, month-only, year/period or unknown date precision.
- Represent prior work in the multi-year comparison even when hours were never recorded; retain the one explicit 47-hour November 2024 record as known partial evidence instead of implying that other billed work had zero hours.
- Order historical harvest cards by sourced picking date with undated variety summaries retained afterward, and keep September 23, 2025 Nerello as the only confirmed exact prior pick date currently available.

## 1.2.37

- Reconcile all 61 CI.MA.LAB samples and 212 measurements against the source workbook with no missing, extra, duplicate, unit or numeric discrepancies.
- Assign the May 2024 wine reports to the preceding 2023 cellar vintage and link the May 2025 Brett samples to their matching April 2025 sample identities, which explicitly identify vintage 2023.
- Preserve the October 2025 malolactic reports in vintage 2025 with an explicit inferred-vintage evidence trail because their source Annata field is blank.
- Store and display how every laboratory vintage was assigned, distinguish confirmed and inferred assignments, expose live laboratory audit counts, and use vintage rather than report calendar year in historical dashboards.

## 1.2.36

- Reconcile treatments whose retained source note already contains the user's authoritative completion confirmation, so they no longer appear as overdue plans.
- Keep completed treatments with unresolved actual application details or PHI checks in a separate harvest-clearance evidence set, preserving safety without mislabeling the work as unfinished.
- Write every approved batch payment to the immutable invoice-payment ledger before marking its records paid, verify the entire block persisted, and make retries idempotent.
- Backfill ledger rows for previously paid approved invoices, reconcile payment status from non-voided deposits, and expose a live integrity count so fully paid invoices cannot silently reappear.

## 1.2.35

- Audit production forecasting with walk-forward historical tests, report its measured error and automatically widen the scenario range when prior performance requires it.
- Exclude the unresolved 2025 liquid-recovery figure from model training until its cellar stage is confirmed, while retaining the source record and reconciliation warning in history.
- Use one audited historical conversion across Operations, the TV and future production totals instead of a separate fixed 70% assumption.
- Assign every newly entered laboratory report linked to a wine lot to that lot's vintage, and group laboratory trends by vintage rather than report calendar year.
- Keep harvest-date forecasts explicitly low-confidence and approval-required while only one sourced exact harvest date and no current numeric maturity samples are available.

## 1.2.34

- Remove only the three newly imported Apple Notes laboratory rows when an identical dated workbook report already exists, preserving the original audited sample and results.
- Verify calendar-overlap reports remain assigned to their wine vintage: 2023 reports tested in April 2025, 2024 reports tested through May 2025, and 2025 reports tested through February 2026.

## 1.2.33

- Make the Apple Notes history migration compatible with the app's statement parser by keeping note punctuation out of SQL delimiters.

## 1.2.32

- Import source-traceable Baiamonte history from Apple Notes, including 2022 variety yields, olive harvest evidence, bottled production, a historical inventory snapshot, and Nunzio work evidence without duplicating canonical workbook totals.
- Record September 23, 2025 as the confirmed Nerello harvest date with 8 people, 164 cassettes and 3,036 kg, and show exact sourced dates when switching dashboard years.
- Import the September 15 and 17, 2023 Baiamonte grape maturity reports as laboratory evidence while keeping them clearly separate from unconfirmed harvest dates.
- Filter the laboratory decision queue, report list and history to the year selected in the dashboard while retaining multi-year comparison charts.
- Assign every lab sample to an explicit vintage: grape and must reports follow their report year, while wine reports retain their linked wine-lot or selected vintage across calendar-year overlaps; repair existing mismatches automatically.
- Feed all valid prior vintage totals, weather/GDD history, exact sourced pick dates, maturity samples, variety-linked laboratory results and clearly labeled estate-level grape reports into future projection and harvest-readiness evidence.
- Preserve conflicting provisional/final quantities as audit notes and expose the Apple Notes evidence in Vineyard Records.

## 1.2.31

- Show source-traceable prior Baiamonte work, compensation and explicit labor hours on the dashboard for the selected historical year.
- Repair Italian day-first and month-only legacy dates already stored in the database, and retain explicit hour values from old payment descriptions.
- Keep current tasks and alerts out of historical-year views and label missing harvest dates honestly instead of implying that a completed historical vintage was not picked.
- Base the production conversion forecast on weighted reconciled grape and wine totals, and attach the available historical weather/GDD years as forecast evidence.

## 1.2.30

- Normalize historical color suffixes so “Nerello Mascalese / red” merges into the canonical Nerello Mascalese row instead of appearing as a duplicate variety.
- Keep the selected year's variety evidence in view instead of always showing the newest vintage.
- Hide current unassigned tank readings and generic current processes from prior-year cellar screens.
- Show reconciled historical grape and wine totals prominently when a prior year has summary evidence but no detailed cellar lots.

## 1.2.29

- Populate selected prior years from reconciled vintage summaries when detailed harvest lots or cellar lots were not historically recorded.
- Apply the year selector to vintage totals, variety cards and charts, cellar history, weather history, olives, treatments, finance, and year-dated work activity without inventing missing detail.
- Keep live weather and forecast values out of prior-year views and label summary-only harvest entries as historical workbook evidence.
- Verify every completed treatment is durably persisted before reporting success.
- Slow the Today TV alert ticker to approximately half its previous speed for comfortable reading.

## 1.2.28

- Import the legacy `BAIAMONTE 2024-2026` work/payment workbook and `Baiamonte Costs Worksheet` into source-traceable historical cost records.
- Include only Baiamonte/TNB expenses; exclude Società La Nave and mixed-company rows that do not provide a safe allocation.
- Retain payments separately from expenses, suppress duplicate Ture summaries, preserve Federico's unsplit 2023/2024 compensation period, and expose yearly expenses/payments in historical comparisons.
- Add historical cost records and the two legacy workbook inputs to the Records screen.

## 1.2.27

- Keep reconciled historical vintage comparisons from double-counting the workbook's `Vintage total` row alongside its individual grape rows.
- Prefer the explicit reconciled total when present and fall back to summing component varieties for older or partial imports.

## 1.2.26

- Add an animated TODAY marker to both TV Intelligence charts, positioned from the current vineyard-local calendar date across the annual temperature and rainfall timelines.
- Limit the marker animation to the visible Intelligence screen so unattended TV rotation does not spend rendering work on hidden charts.
- Keep an open payment/deposit form stable while it is being edited instead of letting the administrator page's background refresh close it and discard the entry.

## 1.2.25

- Allow multiple audited deposits and payments against one approved labor or contractor invoice, with running paid and balance totals plus payment history.
- Sort Approved time by worker by current-year hours, highest first.
- Recognize the working shared Meta/WhatsApp token when reporting Facebook and Instagram configuration health.

## 1.2.24

- Reconcile TV work-plan status from all linked canonical sources so a completed Apple Work Plan item cannot be reopened by a stale Google `needs_action` mirror.
- Deduplicate canonical tasks and shared reminders before calculating overdue and due-today totals.
- Show the live treatment decision window in Next seven days as a clearly labeled prediction requiring review/approval.
- Keep the Work Plan calendar consistent with completion status and render date-only events on their exact vineyard date.

## 1.2.23

- Add an administrator-only Delete record action to the labor correction window with an explicit confirmation prompt.
- Remove the selected labor row from totals and history while retaining its full prior contents in the administrator audit log.

## 1.2.22

- Make each labor-history row point to its exact source record instead of choosing an arbitrary entry that shares the same date.
- Treat a saved administrator correction on an approved imported/manual record as verification and move it from `verification_needed` to `unpaid` while preserving paid records.
- Show undated records as "Date needs correction" and list individual records so duplicate source rows can be corrected independently.

## 1.2.21

- Reflow the complete live label into a height-aware compact tablet layout instead of only adding a scroll container.
- Use a two-column vessel card and denser legal fields on portrait tablets, with an additional short-screen layout for landscape kiosk displays.
- Measure both visual-viewport dimensions and refresh the layout after browser chrome or orientation changes.

## 1.2.20

- Use Android WebView's live visual viewport height instead of a fixed CSS viewport so label content is not cut off by Fully Kiosk browser chrome or orientation changes.
- Give the screen label its own full-height touch scroller while preserving the fixed one-page A4 and 4×6 print layouts.
- Print vessels with a clean stainless outline and accurate liquid fill, without the screen-only glare and bubble layers that produced white diagonal artifacts in PDFs.

## 1.2.19

- Keep A4 labels on one landscape page with white print-safe charts, correctly sized vessel artwork and a compact four-column legal record.
- Rebuild the 4×6 thermal label as a true single-page compact record instead of clipping the lower fields.
- Make tablet labels switch to the stacked layout in portrait orientation even when Fully Kiosk reports a desktop-width viewport.
- Version label assets and disable caching on local display assets so provisioned tablets receive layout fixes immediately after reload.
- Let labor and contractor correction dialogs use the available screen width, scroll their form body and keep save/close controls reachable on short tablet windows.

## 1.2.18

- Draw each cellar label with the correct animated vessel silhouette, wine color, liquid level and fermentation activity instead of a generic horizontal fill bar.
- Show current liters, total liters, hL capacity and the calculated percentage together so vessel volume can be checked at a glance.
- Add a restrained Etna-eruption animation to the Baiamonte label identity, with faster activity during fermentation and full reduced-motion and print fallbacks.
- Add compact recent temperature, density, Brix and pH charts without crowding the core vessel identification.
- Update the legal identity to Azienda Agricola Tenuta Baiamonte S.S. and show Sebastiano Vinci's cellar phone beside his name on every tank label.

## 1.2.17

- Apply the Baiamonte favicon, Apple touch identity and installable PWA manifest across Vineyard Operations, crew entry, TV displays, enrollment and every public cellar label.
- Add a locally generated, no-third-party Start URL QR to the protected Fully Kiosk provisioning panel and link the official Fully factory-reset/device-owner QR generator for complete Android provisioning.

## 1.2.16

- Add a complete installable identity to tank labels and enrolled displays: favicon, Apple touch icon, Android/PWA manifest, maskable icon declaration, standalone/fullscreen metadata and platform theme colors.
- Keep each installed label's start URL and scope on the direct Nabu Casa label gateway.

## 1.2.15

- Register the label and MCP HTTPS gateways even when the installation intentionally keeps Home Assistant's stock login page.

## 1.2.14

- Pass saved enrollment, public label origin and iPad destination options into the running display services so the provisioning profile remains available after an app update.
- Restore the same runtime wiring for saved cellar sensors, planning cadence and account-role options.

## 1.2.13

- Serve the tokenized cellar-label and display-enrollment routes through the existing Home Assistant Cloud HTTPS connection without requiring Home Assistant login.
- Keep the public gateway read-only and restricted to labels, enrollment, brand artwork and display assets; Vineyard Operations administration remains authenticated.
- Allow the configured public label origin to include the hidden Home Assistant gateway path.

## 1.2.12

- Add factory-reset Android display enrollment with a private Fully Kiosk Start URL, hashed device identity, expiring six-digit pairing codes and audited approval or rejection.
- Allow each enrolled display to become either a reassignable tank label or the larger Vineyard Operations display routed to the dedicated `ipad` dashboard.
- Add audited reprovision controls that retire an old tank-tablet identity and return known hardware to fresh short-code pairing.
- Support an optional public HTTPS label origin so read-only tokenized labels can operate outside the vineyard VPN without Home Assistant authentication while administration remains protected.
- Keep the `ipad` password out of provisioning artifacts and direct that display to the configured external Home Assistant URL for a one-time persistent `ipad` login.
- Convert invalid contractor records into one editable, multi-line job invoice and keep fixed-price services in the normal payment workflow.
- Add the official cadastral-map reference plus an editable gold estate-boundary overlay to Atlas.
- Tighten the approved-labor layout and use the available lower edge of the TV Today screen without clipping its navigation.

## 1.2.11

- Separate Giancarlo and Carmela labor, presence and payment totals by exact identity instead of their shared Pafumi surname.
- Add one-off contractor jobs and services, including water delivery, transport, equipment, materials, fuel and tools, to the labor entry and payment workflow.
- Keep reimbursable expenses separate from hourly labor while allowing approved manual labor and fixed-price work to enter the audited payment queue.
- Validate custom workers, hourly entries and fixed-price costs at the labor endpoint and add regression coverage for sibling identity isolation.

## 1.2.10

- Keep operators in Inbox & Review after saving, approving or rejecting incoming information instead of resetting the application to Today.
- Make AI-draft and review modal controls resilient to list rerenders, show an in-dialog save result and add a quick audited rejection form with clear reasons.
- Cache Facebook and Instagram posts between views, refresh incrementally only on request, show compact publishing statistics and support direct JPG, PNG or WebP photo uploads.
- Keep the tank-label release regression check valid across later add-on versions instead of pinning it permanently to 1.2.4.

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
## 1.4.59

- Added a non-persistent vineyard/olive treatment scenario simulator with predicted review timing, verified product candidates, calculated mixture quantities, sprayer batches, PHI screening, stock readiness, and explicit approval blocks.
- Added live field-review requests with block or whole-estate scope, structured photo/count instructions, AI sampling limits, and Work Plan task creation.
- Routed hail through damage and harvest-loss assessment plus a 24–72-hour wound/mold follow-up; treatment prediction runs only when symptoms support a disease target.
- Added a record-by-record treatment safety audit for current label evidence, exact completed-use quantities, sprayer calibration, PHI conflicts, and multi-product mixture verification. Unknown evidence is visibly flagged and excluded from prescription reuse.
- Extracted treatment scenario routes and action history into a dedicated domain module to keep the primary application module within its enforced size budget.

## 1.4.60

- Routed structured Growth Stage reports exclusively to harvest prediction, removing the unrelated treatment recalculation and requiring a variety so evidence cannot land in an unusable unassigned record.
- Added controlled Fruit maturity / ripening progress and Uneven ripening observations; these wait for representative report/photo evidence before refreshing harvest.
- Added an AI harvest-evidence gate so unrelated photo notes cannot silently invalidate pick-date forecasts. Visible maturity, ripening variability, and scope-aware yield risk are returned as auditable route outcomes.
- Kept photographs as supporting evidence only: they cannot infer Brix, pH, acidity, YAN, chemical maturity, picking readiness, or an exact harvest date.
- Expanded harvest evidence with phenology completion percentage and scoped field-loss details, while retaining reviewed, variety-linked current-vintage grape laboratory results as the authoritative numeric maturity input. Maturity samples now also require their grape variety.
- Tightened MCP ingestion so unreviewed/non-grape laboratory records and maturity observations awaiting photos do not trigger misleading harvest refreshes.

## 1.4.61

- Unified quick entry, canonical APIs and MCP ingestion around the same explicit observation routes for damage, disease/treatment, phenology, maturity and harvest evidence.
- Added scope-aware AI damage assessment chains that preserve prior determinations, support whole-estate hail events, distinguish AI estimates from agronomist confirmation and recalculate forecast loss as follow-up reports arrive.
- Added visible photo-analysis status and polling so field submissions move through queued, analyzed, review and failed states without silent pipeline gaps.
- Added treatment simulation, field-review requests, stock shortfalls and safety evidence for labels, applied quantities, calibration, PHI and mixture verification; uncertain records remain blocked from unsafe prescription reuse.
- Reconciled OSSICLOR 20 FLOW with the manufacturer density range and a Baiamonte planning density of 1.40 kg/L while leaving unsupported IMPULSIVE conversions blocked.
- Improved scoped scouting and phenology displays, projection refresh reliability, startup rendering, and the end-to-end integrity audit for current and historical years.
# 1.5.9

- Adds a dedicated Enology bottling workspace that converts one or more traced tank lots into finished-bottle inventory, snapshots every linked legal parcel, records process loss, and clears the source vessels only after physical completion is confirmed.
- Adds editable vintage packaging costs for bottles, corks, front/back labels, capsules and case boxes. The newest matched Fatture in Cloud invoice line takes priority; older invoice, order and quote evidence remains clearly identified as fallback.
- Mirrors detailed Fatture in Cloud document lines so newer supplier prices can supersede prior-year estimates without making Fatture in Cloud writable.
- Seeds owner-authoritative 2023–2025 wine volume and 750 ml equivalent totals while preserving the unknown 2024 grape weight.
- Adds posted product-cost estimates to treatment simulations and completed Agronomist treatment records, with incomplete prices or unit conflicts visibly flagged.
- Separates Damage into its own Agronomy tab, keeps Field focused on observations and phenology, and makes each dated damage card show that report's own Agronomist result, independent system estimate and change from the prior report.
- Compacts Treatments around live decisions and application records, moves infrequent product/sprayer setup into one expandable area, and tightens the Simulator's inputs and calculated-program layout.
- Adds a dedicated annual Fertilization tab for vineyard soil-report uploads, structured laboratory values, year-over-year comparison, conservative screening and an Agronomist-reviewed planning basis that never bypasses Treatments.
