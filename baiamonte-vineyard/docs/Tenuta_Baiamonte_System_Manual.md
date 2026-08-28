# Tenuta Baiamonte Vineyard Operations

## System Manual

**Release covered:** 1.6.93
**Manual date:** 24 August 2026
**System owner:** Azienda Agricola Tenuta Baiamonte S.S.
**Operational authority:** Vineyard Operations MariaDB database

This manual describes what the Baiamonte system does, how staff use it, how its calculations and predictions work, how data moves between services, and how to recognize and recover from problems. It is written for owners, vineyard staff, cellar staff, accountants, agronomists, kiosk users, and technical administrators.

---

## 1. What the system is

Tenuta Baiamonte Vineyard Operations is a private estate-management system hosted as a Home Assistant add-on. It combines vineyard work, harvest, cellar, laboratory, weather, treatment, labor, payment, olive-oil, hospitality, messaging, alert, map, and forecasting functions in one controlled interface.

The core rule is simple:

> MariaDB is the operational authority. Historical workbooks, messages, notes, emails, and laboratory documents are evidence sources, not live databases.

Imported evidence is reviewed, normalized, and written to MariaDB. The dashboards, predictions, labels, payment views, and reports read from MariaDB. The old workbooks are not consulted during normal operation.

### System goals

- Give each role a useful, limited view of the estate.
- Preserve historical records by year and vintage.
- Distinguish facts, estimates, forecasts, and unresolved questions.
- Keep treatment and cellar decisions under human approval.
- Make labor approval and payment auditable.
- Use free, credential-free environmental sources where practical.
- Continue operating through temporary source outages using stored last-good data.
- Keep secrets in protected Home Assistant add-on configuration.

---

## 2. System map

| Component | Purpose | Authority / access |
|---|---|---|
| Home Assistant | Users, devices, dashboards, cameras, weather entities, Supervisor | Home Assistant accounts |
| Vineyard Operations | Main web interface and business logic | Home Assistant Ingress |
| Hospitality | Private tastings, dinners, guest readiness, deposits, and communication history | Hospitality Manager or Administrator |
| Register | Tablet-oriented sales, sellable inventory, receipts, and monthly transaction ledger | Register, Cashier, Hospitality Manager, or Administrator |
| MariaDB | Sole operational database | Add-on network only |
| Baiamonte MCP | Controlled Codex and automation bridge | Bearer token; local/VPN |
| Vineyard TV | Read-only rotating operational display | Viewer profile |
| iPad dashboard | Larger touch operations dashboard | `ipad` viewer profile |
| Cellar labels | Tank identity, live readings, charts, legal identity | Enrolled kiosk URLs |
| Gmail intake | Email and attachment review queue | Protected mailbox credentials |
| WhatsApp | Approved inbound/outbound operational messaging | Meta or system bridge credentials |
| Fatture in Cloud | Read-only accounting mirror | Protected read-only token |
| Public harvest feed | Approved public harvest dates only | Optional publication token |

### Network addresses

- Home Assistant: `http://192.168.0.10:8123`
- Vineyard Operations direct service: `http://192.168.0.10:8101`
- Baiamonte MCP: `http://192.168.0.10:8100/mcp`

Use Home Assistant Ingress for normal staff access. Direct local addresses are intended for service integration, diagnosis, enrolled displays, and VPN use.

---

## 3. Users and permissions

### Administrators

Administrators can manage system configuration, users, process controls, messaging, labor approval, payroll, documentation, and diagnostics. Administrative access should remain limited to trusted owners or system managers.

### Operations users

Operations users can manage vineyard work, harvest, cellar records, laboratory review, olives, treatments, issues, and operational intake. They do not automatically receive full finance or system-configuration access.

### Finance users

Finance users can view the read-only Fatture in Cloud mirror, invoices, payments, expenses, and financial reports. Finance information is intentionally excluded from shared TV and kiosk feeds.

### Worker users

Worker accounts use a simplified personal portal to clock in and out, enter services or expenses, attach evidence, see review status, and view approved history. A worker cannot approve or pay their own record.

### Viewer users

The `display`, `tv`, and `ipad` profiles are read-only. They do not receive finance data or administrative controls.

### Hospitality Managers

Hospitality Managers can manage private tastings and dinners, guest requirements, quotes, deposits, confirmations, arrival, and completion. They do not automatically receive vineyard write, finance, payroll, or system-administration access.

### Register and Cashier users

Register and Cashier users can sell the read-only Fatture in Cloud product catalog, local hospitality packages, and authorized manual items. They can apply a line discount, choose EUR or USD tender, select the Italian or US PayPal Business account, print a non-fiscal operational receipt, and export the monthly local ledger. They do not automatically receive finance, payroll, vineyard-write, or administration access.

Home Assistant People and Users are authoritative for identity, display name, username, profile picture, and presence. Vineyard Operations is authoritative for estate access level, operational role, approval authority, and hospitality permissions. An administrator should assign access and roles in **Admin -> People** rather than creating a second identity.

---

## 4. First use and navigation

1. Sign in to Home Assistant with the appropriate account.
2. Open **Vineyard Operations** from the sidebar.
3. Choose **Operations**, **Agronomy**, **Enology**, **Hospitality**, **Register**, or **Admin** from the top workspace switch. Only authorized workspaces are shown.
4. Choose the working year. Year selection changes the harvest, laboratory, weather comparison, labor, treatment, olive, and historical context.
5. Use the main sections for daily work; use Administration only for configuration or audit tasks.
6. Treat yellow or amber items as uncertain or awaiting review. Treat red items as active exceptions, not automatically as failed equipment.

Changing the working year keeps the current workspace and page open. For example, changing vintage while viewing Enology -> Laboratory refreshes Laboratory for that vintage; it does not move the user to Operations. A page can explicitly show the latest earlier vintage when the selected year has no measurements, but it must label that fallback and must not present it as current-year evidence.

Agronomy and Enology each have a dedicated **Admin** page. Daily pages contain operational evidence and actions; area configuration is kept in that area's Admin page so settings have one authoritative home. Agronomy Admin contains product evidence and catalog overlays plus sprayer calibration. Enology Admin contains the tank register, label-tablet provisioning, blend planning, cellar thresholds, packaging and annual winemaking settings. The operational pages link to these settings without duplicating editable controls.

### Main work areas

- **Today:** current work, recent work, estate status, weather, and alerts.
- **Vines / Harvest:** variety status, harvest plans, actual picks, predictions, and vintage history.
- **Treatments:** forecasts, planned work, approvals, completed applications, and safety evidence.
- **Cellar:** wine lots, vessels, readings, operations, labels, and tank assignments.
- **Labor / Payroll:** work records, approval, contractor invoices, deposits, and payments.
- **Olives:** harvest and oil history, conversion efficiency, cost assumptions, and YoY charts.
- **Laboratory:** reports, vintage assignment, analytes, trends, review, and decision support.
- **Atlas:** cadastral parcels, vineyard blocks, terraces, nursery data, and map geometry.
- **Intelligence:** weather, GDD, seasonal comparisons, prediction evidence, disease pressure, and outlooks.
- **Hospitality:** private experiences, packages, bookings, guest readiness, deposits, and communication history.
- **Register:** tablet sales, sellable inventory, receipts, transaction exports, PayPal account selection, and register settings.
- **Inbox / Messaging:** Gmail and WhatsApp intake, review, contacts, delivery, and replies.
- **Alerts:** current operational alerts and delivery settings.
- **Administration:** process health, users, integrations, logs, documentation, and update controls.

---

## 5. Data authority and evidence rules

Every value should be understood as one of four types:

1. **Fact:** a confirmed measurement or completed event.
2. **Estimate:** a calculated value based on stated inputs.
3. **Forecast:** a future projection with confidence and evidence.
4. **Unresolved:** missing, conflicting, or awaiting human verification.

Blank database values mean **unknown**, not zero. The system should never silently convert a missing quantity into zero.

### Evidence flow

1. A message, email, note, document, sensor reading, or manual entry arrives.
2. The item is stored with its original evidence.
3. Automated extraction may propose structured records.
4. A person reviews material changes.
5. Approved facts are saved to MariaDB with an audit trail.
6. Dependent dashboards and models are refreshed.

### Vintage assignment

Laboratory and cellar reports are assigned to the correct vintage rather than merely the document year. Reports that cross calendar years stay with the wine vintage they describe. Explicit vintage labels and linked wine lots take precedence; inferred assignments remain marked with confidence and evidence.

---

## 6. Intelligence pipelines and decision workflows

The intelligence layer is a collection of evidence pipelines, not one autonomous decision maker. Each pipeline receives evidence, creates a traceable calculation or proposal, identifies missing information, and hands the result to the person or record that has authority. The system may use a provisional result while review is pending only where the workflow explicitly allows it; it never converts a prediction into a completed event.

### Common intelligence contract

Every intelligence result carries the same operating context:

- **Source and timestamp:** where the evidence came from and when it was observed.
- **Scope:** estate, zone, block, parcel, variety, lot, tank, reservation, person, or financial document.
- **Evidence state:** original attachment or message, extracted facts, conflicts, and missing inputs.
- **Calculation state:** model/rule version, result, range, confidence, and explanatory factors.
- **Authority state:** draft, proposed, approved, completed, rejected, superseded, or unresolved.
- **Audit state:** who reviewed or changed the result and what downstream records were refreshed.

An approved fact remains separate from the next system proposal. Recalculation can create a new proposal, but it does not silently overwrite an agronomist-approved loss, an approved treatment, a confirmed harvest plan, a reviewed laboratory result, a sent guest message, or an accounting document.

### Master evidence router

```text
New evidence
  |
  +-- hail / frost / wind / physical injury
  |      -> damage event chain -> yield impact proposal
  |
  +-- mildew / mold / pest / disease symptom
  |      -> disease pressure -> treatment review
  |
  +-- phenology / berry maturity / grape laboratory result
  |      -> harvest readiness -> harvest forecast
  |
  +-- wine or must laboratory result
  |      -> enology review -> lot and cellar history
  |
  +-- weather observation or forecast
  |      -> disease, treatment timing, harvest and alerts
  |
  +-- email / message / uploaded document
         -> extraction review -> approved domain record
```

The submitter chooses the observed condition and growth stage from controlled lists. The router preserves the original evidence and can attach a new observation to an existing issue chain, such as the estate-wide 2026 hail event, instead of creating a duplicate event.

### Damage assessment and forecast-impact pipeline

Damage intelligence estimates crop impact while keeping the system estimate independent from the agronomist's final decision. Estate-wide means 100% geographic coverage of the estate; it does not mean 100% yield loss.

```text
Event or follow-up report
  -> identify event chain and geographic scope
  -> evaluate structured scouting and optional photos
  -> calculate AI loss %, range and confidence
  -> compare with earlier reports and approved final
  -> create a new proposal for the chain
  -> agronomist reviews and approves or edits
  -> approved chain final adjusts the harvest forecast
```

Each report card shows the result produced by that report. The chain summary shows the current system proposal, the latest approved agronomist value, and the percentage currently used by forecasting. Follow-up reports refine the chronological assessment; they do not rewrite the historical result of an earlier card. Until an updated proposal is approved, the last approved chain final remains authoritative. If no agronomist value exists yet, the clearly labelled provisional AI value may feed planning with its confidence range.

### Disease pressure and treatment pipeline

Weather, disease pressure, field scouting, crop, growth stage, treatment history, product evidence, inventory, sprayer configuration, and harvest clearance operate as one decision chain. Vineyard and olive programs are evaluated separately.

```text
Weather + field evidence + crop stage + treatment cadence
  -> calculate disease/stress pressure by target
  -> decide whether review is needed
  -> screen crop-authorized products and support products
  -> check season, target, rate, PHI/REI and compatibility
  -> calculate homogeneous mixture and sprayer batches
  -> compare required quantity with the inventory ledger
  -> find a defensible application window
  -> agronomist approves product, date and instructions
  -> operator records the completed application
```

The output can contain a primary disease-control product plus justified nutrition, wound support, wetting, resistance-management, or other support products. A product is included only when its current label/formulation evidence supports the crop, target, rate, unit, timing, and combination. Separate passes are shown when same-tank compatibility is not verified. Every prepared tank is treated as a homogeneous mixture under agitation.

The treatment simulator replays the same evidence and rules for a hypothetical or historical date but saves nothing and authorizes nothing. It shows the proposed products, amounts, batches, timing, evidence gaps, on-hand stock, shortage, and total required inventory. A negative stock ledger is permitted when completed use precedes a delayed invoice; the shortage remains an operational issue until a receipt nets it or an authorized person resolves it as not needed for the rest of the season.

For Baiamonte vineyard work, the default operating picture is one pass over the complete selected vineyard area using 400 L total carrier, prepared as two 200 L fills with the same approved recipe. The simulator adds only products supported by the current target, field evidence, crop stage, historical Agronomist pattern, inventory and label rules. It does not add a nutrition, support or disease-control product merely because the product exists in inventory. When exact same-tank compatibility is not recorded, the program remains blocked or separates the pass for Agronomist review.

The disease model recalculates pressure from GW2000 temperature, humidity, rainfall, leaf wetness when available, soil moisture when available, wind, solar conditions, phenology, maturity evidence, localized scouting and recent treatment context. Weather is the principal rationale for timing, while field evidence determines whether pressure is actually actionable. The model also creates disease-onset forecasts, block-specific calibration, spray-window evidence, expected product duration, retreatment cadence and resistance-rotation review. These learned outputs remain provisional until sufficient reviewed outcomes exist.

Agronomist review records the accepted risk level or corrected score and the reason. Paired pre/post-treatment scouting links the last comparable observation before treatment with the first comparable observation after treatment. Only these field-observed pairs can train effectiveness by disease, mixture, dose, block and weather; reconstructed weather pressure is context, not proof of treatment success.

### AI and learning supervision

Admin -> AI is the full monitoring page for learning processes. It shows model version, data-through date, evidence counts, represented seasons, validation method, measured accuracy or error, data-quality findings and release gates. A model can be active while remaining review-gated. Low accuracy, too few seasons, missing Agronomist decisions or missing paired outcomes must be shown as limitations rather than converted into confidence.

Current learning processes include laboratory vintage projection, harvest-date learning, Agronomist treatment-pattern learning, disease-pressure calibration, disease onset, treatment effectiveness, product duration and retreatment cadence, FRAC rotation, young-vine nutrition, block disease calibration, spray-window learning and automated data-quality detection. New treatment, scouting, laboratory and Agronomist-review evidence rebuilds the connected learning records and feeds the live Agronomy, Treatments, Laboratory, Harvest, Alerts, WhatsApp and Admin views. Human approval boundaries remain authoritative everywhere.

The cistern camera remains an always-on local RTSP and Eufy source. Its scheduled level check briefly enables the camera's paired light when needed, extracts one current frame from the continuous local stream, restores the prior light state and leaves the stream untouched. A bridge-generated still and then a sleeping-source wake-up are fallbacks only. Camera AI remains the operational visual estimate while the local shadow model learns side by side. Repeated frames and repeated percentages do not satisfy the release gate: the panel separately reports unique frames, observed changes, distinct accepted levels and the recorded level range. A physical gauge or confirmed dip measurement remains the preferred calibration reference whenever one is available.

Vineyard North also supports a protected local RTSP source for future fixed-view visual evidence. Suitable future uses include coarse canopy-color change, storm or hail aftermath, smoke, obstruction and scene-change screening. The distant view must not be treated as proof of a disease, pest, phenology stage or treatment need; any such finding remains advisory and must be confirmed by localized scouting or the Agronomist.

### Harvest prediction pipeline

```text
Historical harvest dates and GDD model
  + current weather and ensemble spread
  + phenology, scouting and maturity samples
  + reviewed grape laboratory chemistry
  + damage-chain approved/provisional loss
  + treatment PHI, work readiness and cellar capacity
  -> variety forecast date/window and yield range
  -> confidence, evidence age and missing-input warnings
  -> authorized harvest plan
  -> actual pick record becomes the historical fact
```

The learned model retrains when authoritative evidence changes and reports represented years, training count, back-test error, confidence, and important factors. On-site weather and verified field/laboratory evidence carry the operational weight. Open-Meteo ensemble spread expresses near-term uncertainty; SIAS validates regional conditions; Sentinel-2 supplies block-level vegetation trends; ECMWF seasonal anomalies support early planning only. None of the external sources can independently order a pick.

### Laboratory ingestion and enology pipeline

```text
Original report or image
  -> retain viewable source
  -> detect every sample section on every page
  -> extract sample/lot, Annata, analytes, values and units
  -> split multi-sample reports into linked result groups
  -> assign grape variety, wine lot and vintage
  -> compare source/result signature for duplicates
  -> human review of conflicts and assignments
  -> save once -> refresh harvest or enology intelligence
```

`Annata` normally means the wine vintage. A report date in the following calendar year does not move the result to the newer vintage. For grape samples, variety and sample date route the result to harvest readiness. For must and wine samples, the linked lot and vintage route it to enology and cellar history. Exact source/result signatures prevent a report or extracted result from being imported twice.

### Messaging and document-ingestion pipeline

```text
Gmail / WhatsApp / Apple message / uploaded document
  -> store source and sender context
  -> classify likely domain and extract explicit facts
  -> show uncertainty, conflicts and proposed records
  -> reviewer approves, corrects or rejects
  -> approved record enters its domain pipeline
  -> replies or notifications require an explicit send action
```

If no explicit facts can be supported, the item stays in review instead of generating a guessed record. Messages cannot complete treatments, clear reminders, approve payments, alter harvest dates, or create financial facts merely because their wording resembles an action.

### Hospitality inquiry, reservation and partner-commission pipeline

```text
Matched inbound subject or manual inquiry
  -> guest inquiry and response history
  -> reservation conversion and availability check
  -> optional partner assignment and commission rule
  -> estimated commission while the visit is tentative
  -> earned/due commission when the qualifying visit is confirmed
  -> approval -> one or more partner payments
  -> paid/void state and Finance payable reconciliation
```

Partners are managed as hospitality business records with contact, tax/payment notes, default commission method, rate, and active state. Each reservation keeps its own commission snapshot so later partner-rate changes do not rewrite history. Estimated commissions are not Finance payables. Only earned due, approved, or partially paid balances enter the payable view; cancelled or disqualified reservations void the commission while preserving the audit trail.

### Alert and operational-action pipeline

```text
Sensor, scheduler, inventory or database condition
  -> evaluate threshold and evidence freshness
  -> create/update one durable alert
  -> rank by severity and route configured copies
  -> show the same authoritative state on web and TV
  -> clear only when the measured condition or owner action resolves
```

Alerts are durable database records. Delivery channels send copies; they do not own alert state. A reminder, work-plan item, or notification cannot be marked satisfied by an unrelated duplicate or stale completion.

### Decision authority summary

| Pipeline | System may calculate | Final authority |
|---|---|---|
| Damage | Provisional loss, range, confidence, trend | Agronomist-approved chain final |
| Treatments | Pressure, products, mixture, stock gap, date window | Agronomist approval and completed application record |
| Harvest | Variety date/window, yield range, confidence | Authorized plan; actual pick is final fact |
| Laboratory | Extraction, sample grouping, vintage proposal, duplicate check | Reviewed saved result and linked lot/vintage |
| Messaging | Classification and proposed records | Human review and explicit send/save action |
| Hospitality | Availability, lifecycle prompts, commission calculation | Authorized reservation and commission/payment actions |
| Alerts | Detection, severity, routing and automatic clear evidence | Authoritative measured state or explicit resolution |

---

## 7. Vineyard, harvest, and historical records

### Harvest records

The system stores planned quantities separately from actual harvest lots. Actual pick dates, weights, crates, blocks, varieties, and source evidence drive historical reports and forecasting.

A single picking lot can include multiple legal cadastral parcels. Select every contributing parcel when recording the pick; the database keeps each parcel as a separate authoritative relationship rather than combining the references into notes. When that picking lot is transferred into a cellar lot and tank, every linked parcel follows the trace automatically. Additional picking lots can enter the same tank and their fruit and must quantities accumulate.

Each live and printed tank label lists the deduplicated legal provenance for its current wine lot: municipality, cadastral sheet, parcel number, vineyard area, tenure, and contract protocol when recorded. The label derives this list from the retained harvest-to-tank trace and does not require the parcel information to be typed again.

Authoritative harvest dates currently include:

| Vintage | Grecanico | Grenache | Nerello |
|---|---:|---:|---:|
| 2023 | 23 Sep | 24 Sep | 8 Oct |
| 2024 | 11 Sep | 23 Sep | 23 Sep |
| 2025 | 11 Sep | 17 Sep | 23 Sep |

The 2024 Grenache and Nerello harvest date is shared. Earlier conflicting date lists were discarded by owner instruction.

### Year switching

Changing the year must change the visible harvest, work, laboratory, treatment, weather, olive, labor, and financial context. Current live data and historical evidence use the same database, so comparisons do not depend on reopening old workbooks.

---

## 8. Harvest prediction logic

Harvest predictions are decision support, not autonomous picking instructions. Sebastian or another authorized person confirms the operational decision.

### Authoritative inputs

- Confirmed historical pick dates by variety.
- On-site GW2000 weather history.
- Base-10 growing degree days (GDD).
- Current deterministic weather forecast.
- Fresh ensemble forecast spread.
- Variety-assigned grape laboratory results.
- Maturity samples, phenology, and field reports.
- Treatment clearance and pre-harvest intervals.
- Work readiness and cellar capacity.
- Historical model error and year-over-year behavior.

### GDD calculation

Daily GDD uses:

`max(0, ((daily minimum C + daily maximum C) / 2) - 10)`

If minimum and maximum are unavailable, an approved daily-mean fallback may be used and is labeled. The calculation accumulates from the configured season start and is compared with variety-specific historical behavior.

### Learned-model behavior

The learned model uses prior vintages as training evidence. It reports training sample count, represented years, confidence, and back-tested mean absolute error. It is recalculated when authoritative evidence changes.

New grape laboratory results, maturity samples, phenology observations, harvest plans, treatment changes, or harvest records create a durable refresh request. The scheduler processes the request rather than waiting for the normal full prediction interval.

### Laboratory influence

Fresh, reviewed, variety-assigned grape laboratory data can affect readiness. Unreviewed reports or grape results older than 21 days cannot directly move the date. As harvest approaches, laboratory chemistry and field maturity receive more weight than coarse seasonal outlooks.

### External sources and limits

| Source | Use | Restriction |
|---|---|---|
| Open-Meteo ensemble | Near-term uncertainty and forecast spread | Automatic date influence bounded to plus/minus one day |
| SIAS regional data | Independent validation | Does not replace the on-site station |
| Sentinel-2 | Parcel/block vegetation trend evidence (NDVI, NDRE, LAI estimate) | Cannot independently select a picking date |
| ECMWF seasonal | Early rainfall and temperature planning | Coarse scale; cannot set an exact date |

The system uses free data without required credentials for these sources. Sentinel processing currently recognizes seven verified cadastral parcel polygons and reports the geometry scope explicitly.

---

## 9. Treatments and safety

The treatment workflow is **plan -> review -> approve -> apply -> record**.

- A forecast or model recommendation is not an approved treatment.
- A planned treatment is not a completed application.
- Completion requires actual date, product, rate, area, operator, and safety evidence when applicable.
- Agronomist review remains required for disease and treatment recommendations.
- Pre-harvest and re-entry intervals must be preserved.
- Missing safety detail is visibly flagged rather than guessed.

### Projection configuration

The Home Assistant add-on configuration provides two planning defaults:

- `treatment_planning_water_l`: the provisional total carrier-water volume. It defaults to 400 L and can be changed in the Treatments page for a live calculation.
- `treatment_default_sprayer`: the name, model, or internal ID of the preferred active spray-equipment profile. The Treatments page also provides a selector when more than one profile exists.

Sprayer capacity, usable fill, nozzle setup, flow, pressure, travel speed, carrier rate and calibration status remain database equipment records. A nominal tank size may split a projection into batches, but the proposal remains blocked until the actual usable fill and field calibration are verified. Product projection requires a verified formulation, estate authorization, current crop/target use, documented rate and compatible units. Water-based and per-hectare rates are calculated directly; density or mass/volume conversions are never guessed. Products with incomplete directions remain visibly marked as needing configuration and are not automatically included.

Current source-backed product directions include these explicit method limits:

- Frontiere: vineyard foliar support at 0.75–1.00 L/ha; it is not automatic disease control.
- Ferticus 18 M: vineyard foliar nutrition at 300–500 g/100 L. The system preserves this as a mass rate and never displays it as millilitres.
- TerraPlus Solub NPK 8-7-6: 15–30 kg/ha per pass as a separate, localized soil-directed spray (or fertigation). It must not be presented as a canopy spray, must not be mixed automatically with crop-protection products, and its mother solution must not be acidified or mixed with calcium.
- Ossiclor 20 Blu Flow: vineyard copper application at 1.7–4.2 L/ha under the current authorized use, with crop stage, annual copper limits, PHI, weather, PPE and Agronomist approval checked before use.

Support and nutrition products remain unselected by default. A risk score alone never adds them to a treatment. Every projected use continues to require the current container directions and human approval.

The current audit has no open treatment safety-gap failures. Seven older applications remain explicitly restricted historical evidence because contemporaneous label, calibration or exact-use facts cannot be reconstructed. Restricted history may inform chronology but cannot be reused as verified safety evidence.

### Fertilizer and young-vine nutrition separation

Fertilizer procurement shows land and whole-vineyard soil products only. Vine foliar products do not belong in that procurement list. TerraPlus is reserved for the mapped section of small, young vines and appears in the young-vine nutrition evidence instead of the general fertilizer recommendation. The system may recommend TerraPlus only when mapped vine age plus recorded weak growth, chlorosis, establishment stress, verified deficiency, tissue evidence or soil evidence supports review. It never recommends TerraPlus simply because it was purchased or is on hand.

---

## 10. Laboratory reports

The laboratory section stores original reports, sample identity, vintage assignment, matrix, variety or lot linkage, analytes, values, units, review state, and interpretation.

### Correct operating sequence

1. Import or upload the original report.
2. Confirm sample name, sample type, report date, and vintage.
3. Link grape reports to a variety and wine reports to the correct lot when possible.
4. Check units and decimal interpretation.
5. Review extracted results.
6. Save the review decision.
7. Allow the prediction or cellar decision-support refresh to run.

The current finding card analyzes only the newest measured report for the selected vintage and states its source and review boundary. The measured trajectory and projected endpoint compare only the same normalized wine identity, sample type, process stage, analyte and unit. Historical endpoints use the final matching measured result from each earlier vintage. AI-assisted values are recalculated when a new numeric result arrives and are constrained to physically possible nonnegative values. An approved marker is displayed separately from a prediction and is never invented when a variety standard has not been configured.

Historical names are normalized for comparison while the original source label is retained. `Nerello`, `Nerello Mascalese`, `Narello Macalase` and vintage-suffixed forms refer to the same Nerello Mascalese identity. Documented Grecanico/Bianco-Grecanico and Grenache spelling variants are handled similarly. Grape, must, wine and other sample types remain separate and are not merged merely because their names match.

The durable laboratory model stores each prediction at its historical cutoff and scores it only against a later actual result. Future measurements never enter an earlier prediction input. Direction accuracy below the release threshold keeps projections review-gated. Nine laboratory records are currently flagged for genuine source review; the authoritative report index has no missing, incomplete, wrong-type or duplicate sample groups after normalization.

---

## 11. Cellar and tank labels

The cellar module tracks physical containers, wine lots, volume, phase, manual or sensor readings, and operations. A planned container assignment is not the same as physical occupancy.

### Tank labels

Each physical tank keeps a stable label URL. Changing the assigned wine updates the label contents without changing the tank URL. Labels include:

- Tank identity and correct vessel type.
- Capacity, contained volume, and calculated level.
- Wine/vintage/lot information.
- Recent temperature, density, Brix, and pH readings.
- Small recent-reading charts when space permits.
- Legal company identity and cellar contact.
- Browser favicon, Apple touch icon, and Android/PWA identity.
- Responsive layouts for different tablet sizes and print layouts.

Cellar displays are enrolled inside the VPN. They can then operate through the approved outside connector. The direct Nabu Casa address is the preferred outside label route; the URL remains available as a backup when QR provisioning is unsuccessful.

### PLAATO V2 Pro automatic monitoring

PLAATO V2 Pro is available as a dedicated automatic tank-reading mode. In Home Assistant App Configuration, add the protected `plaato_api_key` generated in the PLAATO account integration page, then map each tank with `plaato_tank_mappings` in the form `T-01|PLAATO batch-or-device-ID,T-02|another-ID`. The mapping may use a batch, device, barcode, or fermenter identifier/name returned by the official PLAATO API. Keep identifiers unique.

Release 1.6.93 starts with the local-only `demo` key so the fermentation interface can be evaluated immediately. This sentinel never contacts PLAATO Cloud and generates moving, PLAATO-shaped telemetry for every active tank. Replace `demo` with the official API key and add explicit tank mappings before relying on live production readings.

After saving the add-on configuration, open Enology → Cellar → Vessel & reading, edit the mapped tank, and select **PLAATO V2 automatic**. The tank card and tank label then show:

- Live temperature, specific gravity and PLAATO Plato.
- Derived recent gravity drop in milli-SG per hour and a seven-day gravity trend.
- Original/final gravity, estimated ABV, attenuation, batch identity and start date when supplied by PLAATO.
- Battery, Wi-Fi, firmware, raw sensor frequency, reading age and connection state.

Selecting a tank in either Cellar or Enology opens the full fermentation panel. It contains the measured temperature and gravity graphs, a dashed forward gravity projection, every raw PLAATO sample retained in the seven-day window, batch and device details, and the complete linked cellar-process timeline. Calculated progress, phase, current alcohol estimate and finish timing state their method and confidence. An estimated finish is produced only when PLAATO supplies a final-gravity target and the recent measured rate is usable; it remains informational until the enologist confirms the cellar action.

The integration is read-only and cached to protect the sensor cloud and Home Assistant. It does not operate cellar equipment. PLAATO batch volume is context only and is never treated as a continuous tank-level measurement. Tank volume and pH remain manual or come from separately mapped Home Assistant sensors. A stale or unavailable PLAATO reading raises a visible monitor fault without erasing the last trusted cellar record. Switch the tank back to Manual before entering a manual sensor reading.

---

## 12. Olive oil records and cost logic

The olive section compares harvested olive weight, oil liters, conversion efficiency, total modeled cost, and cost per liter by year.

### Confirmed 2024 result

- Olives: 332 kg
- Oil: 40 L
- Conversion: 8.3 kg olives per liter
- Oil yield: 12.048 percent by the system's liters-per-kilogram comparison

### Editable 2024 cost assumptions

- Pressing: EUR 0.20 per kg of olives.
- Bottle and label: EUR 2.30 per 500 ml bottle.
- Planned bottles: 220.
- Supplier invoice: EUR 751 net plus 22 percent VAT.
- Annual labor: EUR 1,000.
- Harvest labor reference: EUR 540 at EUR 7 per tree, included in annual labor by default.

The supplier invoice is treated as including pressing and bottling by default, preventing duplicate cost counting. The correct formulas produce:

- Pressing component: 332 x EUR 0.20 = EUR 66.40.
- Bottling component: 220 x EUR 2.30 = EUR 506.00.
- Supplier gross: EUR 751 x 1.22 = EUR 916.22.
- Total with annual labor: EUR 916.22 + EUR 1,000 = EUR 1,916.22.
- Cost per actual oil liter: EUR 47.91.
- Actual 500 ml bottle equivalents from 40 L: 80.

The planned 220 bottles require 110 L, so they exceed the confirmed 2024 oil volume by 70 L. Cost assumptions can be edited and saved per year.

### Olive harvest outlook

The Olive page displays an estimated harvest date and uncertainty window from exact Baiamonte olive harvest dates stored in MariaDB. Year-only notes are excluded. With only a small number of exact seasons, the system correctly reports low confidence. A current-year recorded harvest date replaces the estimate and is labeled as an actual date. The calendar estimate is planning support only; fruit maturity, oil accumulation, crop condition, weather, and mill availability still require field confirmation.

### Separate olive treatment program

Every treatment belongs to either **Vineyard** or **Olives**. The two histories, forecasts, summaries, entry controls, learned weather precedents, effectiveness profiles, duration profiles, spray-window profiles, and FRAC-rotation sequences are separate. Vineyard disease-pressure scores and learned treatment cases are never reused to predict an olive treatment.

The olive treatment workspace screens **olive fruit fly** and **olive peacock spot** from the current weather, olive stage, trap or fruit findings, visible leaf symptoms, treatment history and paired before/after scouting. Weather may open a monitoring window, but it cannot select a product by itself. A calculated olive program requires matching field evidence, a current reviewed Italian olive crop-and-target use, a verified formulation and rate, exact grove area, sprayer and carrier configuration, inventory reconciliation, PHI clearance, compatible mixture evidence and Agronomist approval. The simulator supports current and historical olive scenarios, displays one-pass batch recipes, and saves nothing until an operator records and approves a plan.

The recorded 2026 olive treatment is retained with its exact products, dose basis, water volume, and calculated totals. Historical 2025 workbook entries are retained as completed olive work, but their missing products, doses, target, and safety details remain visibly unverified.

The system can suggest what to apply only after a database record confirms the exact crop, target, current Italian authorization, recent label verification, dose range, PHI, REI, and related restrictions. If those fields are incomplete, the product recommendation fails closed. The Agronomist must approve every candidate before application.

---

## 13. Labor, contractor invoices, and payments

Labor and contractor records move through review and payment states. Hours, fixed services, reimbursements, and invoice payments are stored separately enough to preserve an audit trail.

### Standard workflow

1. Worker or manager records hours, service, expense, or invoice evidence.
2. The record is submitted for review.
3. An administrator corrects or approves it.
4. Approval locks the payable basis.
5. One or more deposits or payments can be recorded against an invoice.
6. The payment ledger determines paid, part-paid, or unpaid status.
7. Fully paid items do not reappear in the payment queue.

The current payment-integrity audit shows no paid-ledger mismatches, no fully paid items reappearing, no partial-payment status errors, and no verification holds. Six non-payable records are marked paid; they are tracked as a data-quality category and do not create a current payment mismatch. The formerly future-dated labor entry was corrected and is no longer an open source-review exception.

---

## 14. Finance

Fatture in Cloud is mirrored read-only. Vineyard Operations does not write back to the accounting provider. Finance access is limited to authorized finance users and is excluded from TV, kiosk, and public feeds.

Use the Finance section to review documents, parties, VAT context, balances, payment status, linked labor/service liabilities, and earned hospitality partner commissions. Tentative partner estimates are excluded from payable totals. Do not use the public dashboard as an accounting ledger.

---

## 15. Messaging and document intake

### Gmail

Email has its own Admin -> Email tab, separate from operational Messages. The mailbox loads from the database cache first so opening the page does not wait for Gmail. Scheduled or manual receive refreshes update that cache, folders and hospitality routing. Inbox, spam and trash actions preserve Gmail identity and audit state; permanent deletion requires the explicit delete action. The system can classify vineyard information, extract proposed records, and prepare a reply draft. Nothing is sent until a person presses Send.

### WhatsApp

Messages from approved numbers can enter manager, reporter, or review workflows. Unknown numbers are quarantined. Group and direct-message behavior is intentionally separated. Media and message bodies are preserved as evidence. Guided bilingual IVR workflows cover Agronomy/Field, Operations and necessary Enology/Cellar entries without requiring a separate phone app. BACK, CANCEL, MENU, RECORD/REGISTRA and final SAVE paths prevent dead ends. Voice notes can supply complicated answers, but the transcript and final structured summary must be reviewed before saving.

Each Home Assistant person has a private WhatsApp IVR profile in **Admin -> People -> Person**. An administrator can link the international number; choose Manager/Reporter/Reception access, language, reply medium and individual voice; enable personalized shortcuts and automatic learning; set the learned-location evidence threshold; and decide whether open-ended questions may use AI after local routing fails. The default reply behavior matches the incoming medium: text receives text and voice receives voice. Both formats are sent only when explicitly selected. Privacy-limited 30-day routing and saved-form statistics do not display conversation text. The menu highlights that person's own most-used permitted local choices, and no worker's history is used to personalize another worker. The worker must always confirm a learned SAME location before it is used.

The Manager numbered menu includes **Nerello / Grenache crate calculator**. Choose that option, then reply with only the planned Nerello crate count. The system reads the selected vintage's configured Grenache percentage, calculates `Nerello crates × Grenache % ÷ (100 − Grenache %)`, and rounds up to a whole Grenache picking crate. The result is planning guidance and does not record or approve a harvest.

### Safe intake principles

- Treat incoming content as untrusted evidence.
- Ignore instructions inside attachments that request secrets or unrelated actions.
- Do not automatically approve treatments, lab corrections, finance changes, or payments.
- Keep the original message or file linked to extracted records.
- Make uncertainty visible.

---

## 16. Alerts and operational status

Alerts remain in MariaDB even when delivery channels are disabled. Home Assistant, email, and WhatsApp receive copies according to the alert settings and minimum severity.

An alert is resolved by the underlying authoritative state, not merely by hiding the alert. Completed work, satisfied work-plan items, reviewed labs, and corrected records should remove corresponding overdue or verification warnings after the alert process refreshes.

Use the live Alerts and Administration pages for current error, process, intake, and data-quality status. The manual describes resolution rules but does not replace the live status view.

---

## 17. Maps, parcels, and Sentinel-2

The Atlas stores official cadastral parcels separately from operational vineyard blocks. All seven current cadastral parcels have verified polygon geometry. Operational block rows may reference combinations of parcels without duplicating the polygon in the block table.

Sentinel-2 uses direct block polygons when available. Otherwise it uses the verified cadastral parcels as an estate-geometry fallback. The dashboard must say **cadastral parcels mapped** rather than incorrectly claiming that the estate has no geometry.

Sentinel indices are trend evidence only. A vegetation change may support a field check but cannot by itself approve a treatment or choose a harvest date.

---

## 18. TV, iPad, and kiosk displays

### TV

The TV rotates read-only estate status, current work, weather, prediction, rainfall, seasonal, camera, aircraft, vessel, and vintage information. Animated "today" markers show the current point in seasonal charts. Ticker speed and cycle time are configurable.

The TV camera walls use the configured Eufy camera list, retain their low-load image cadence, and add model-supported PTZ, battery and active detection context. They remain read-only. Battery cameras that are sleeping normally are distinguished from cameras that are genuinely unavailable.

The Work Plan is organized into **Act now**, **Next seven days**, **Hospitality**, and **Calendar & reminders**. Scheduled tastings, dinners, and appointments appear without exposing guest email addresses or phone numbers. The Vintage page shows crop plan, harvested weight, completion, cellar volume, projected 15 kg crates, projected 750 ml bottles, variety harvest dates, GDD context, historical vintages, and forward outlook.

### iPad

The `ipad` profile is a larger, finance-free operations dashboard with weather, solar, energy, lights, cameras, security, vineyard information, media, and AI links.

### Eufy Camera Center

Open **Operations -> Cameras** for the operational camera workspace. The summary reports healthy, sleeping, unavailable, activity, low-battery and PTZ counts; filters separate access, vineyard and building cameras. Home Assistant cards use the current app-style camera cover maintained by the bridge, not the smaller event-thumbnail entity. Covers are refreshed serially on a bounded cadence and cached, so opening the page does not start every camera stream or wake every battery camera. Live viewing is explicitly started for one camera and is stopped when its dialog closes.

Movement, 360 rotation, saved positions and calibration appear only when that exact camera advertises the capability. Camera power, light, motion detection, motion tracking, auto night vision and recording switches are likewise capability-checked. Administrators may save or delete supported PTZ positions and send a verified canned doorbell response. The server independently rejects unsupported or unauthorized commands. Alarms, locks, microphones and speakers are intentionally excluded from ordinary operations.

Eufy's on-device motion, person, vehicle, pet and doorbell classifications are copied into a durable estate event log with their camera, area, transition times and cached evidence link. No raw recognition payload is stored and the application performs no new facial inference. Operators may mark events reviewed. Genuine camera outages must persist for fifteen minutes before creating an alert; two or more outages in one area create shared power, network and station guidance. Those alerts automatically enter Today, TV, WhatsApp and the normal review inbox.

The always-on Vineyard North stream also supplies a separate, low-load fixed-view evidence pipeline. It samples no more than hourly, rejects dark, washed-out or low-detail frames, measures scene and canopy-color change locally, and invokes contextual AI interpretation only for the first suitable baseline, the daily review, or a material change after a bounded interval. The resulting Today and TV card can show visibility, operations, canopy signal, frame change and a conservative inspection prompt. Weather, recent work, scouting and treatments are explanatory context only. Camera evidence never diagnoses disease, identifies a person, approves a treatment, or replaces a field inspection. Ordinary review alerts require repeated suitable evidence; a high-confidence fire or smoke observation may escalate immediately.

### Tablet labels

Tank-label devices use a dedicated enrollment flow. Each registered tablet has a permanent label URL and its own QR code. Already visited label pages, branding, and the last successful tank reading are cached so a label can reopen and remain useful during a temporary connection outage.

For a factory-reset Android tablet, open **Enology -> Tablet setup** and scan the managed-device QR during Android's initial setup. The add-on hosts a checksum-pinned Fully Kiosk Browser EMM installer locally and supplies a private one-page profile that launches the assigned label after boot, stays in landscape kiosk mode, recovers after connectivity changes, and enables local-network Remote Admin. The separate Start URL QR remains available as a manual fallback. Reprovision controls should replace the device identity cleanly rather than creating duplicate tablets.

---

## 19. Hospitality

Hospitality is an internal, low-volume booking and service workspace for private estate experiences. The current release supports one private guest party at a time and is designed for tastings and dinners for approximately 6 to 12 guests.

### Packages

Administrators and Hospitality Managers can maintain the active package name, description, minimum and maximum guest count, duration, base price, per-person price, deposit requirement, inclusions, and preparation notes. The initial packages are:

- Private Estate Tasting: 1 to 6 guests.
- Cellar Tasting & Pairing: 2 to 8 guests.
- Private Estate Dinner: 6 to 12 guests.

Pricing remains configurable and quote-based. Saving a package changes future selection options; it does not silently rewrite a confirmed guest quote.

### Gmail inquiry routing

Hospitality Admin controls a list of inbound Gmail subject phrases. The initial phrase is **Inquiry about Reserve Tasting**. Matching is case-insensitive and ignores common Reply and Forward prefixes. More phrases may be added one per line without changing protected Gmail credentials.

Matched public messages enter **Hospitality -> Guest inquiries** even when the sender is not on the vineyard operations allowlist. They are safe requests, not approved operational records. Attachments continue through the protected intake safeguards. Existing matching Gmail records are reconciled as well as new mail.

Open an inquiry to read it, prepare and explicitly send an email response, change its state, add internal notes, or convert it into a reservation. Conversion pre-fills the available guest identity and source, then requires the operator to choose the package, date, time, guest count, and booking state. The inquiry is linked to the resulting reservation.

### Reservation workflow

1. Record the inquiry and select a package, date, time, and guest count.
2. Capture the guest name and only the contact details needed for service.
3. Record dietary restrictions, accessibility needs, celebration details, preferences, internal notes, quote, and deposit.
4. Move the reservation through requested, confirmed, arrived, completed, cancelled, declined, or no-show states.
5. The server rejects overlapping confirmed or arrived experiences so only one private guest party is committed at a time.
6. Send email or WhatsApp confirmation only by pressing the explicit communication action. Phone calls and notes can be recorded without sending a message.
7. Open any reservation to update its details or delete it after confirmation. Deletions remain in the audit trail; a linked inquiry returns to the responded queue.

The hospitality communication log preserves channel, subject or summary, operator, delivery state, and timestamp. Guest contact details remain inside the protected workspace and are intentionally omitted from TV data.

### Partner management and commissions

Hospitality Admin includes a partner database for concierges, hotels, travel advisors, event organizers, and other referral sources. A partner record stores the organization and contact details, commission method and default rate, tax/payment notes, status, and internal operating notes.

Assigning a partner to a reservation creates a reservation-specific commission snapshot. A percentage rule uses the eligible reservation amount; a fixed rule uses the saved fixed amount. The operator may change the reservation commission without changing the partner's future default.

Commission states follow the reservation lifecycle:

1. Inquiry or requested reservation: estimated only; not payable in Finance.
2. Qualifying confirmed/arrived/completed reservation: earned and due.
3. Approved commission: authorized for payment.
4. Partial payment: remaining balance stays due.
5. Paid: payment ledger equals the earned amount.
6. Cancelled, declined, no-show, or otherwise disqualified reservation: void, with history retained.

One commission can receive multiple payments. Each payment preserves amount, date, method, reference, note, and operator. Corrections are audited; deleting a payment is restricted and does not erase the original commission or reservation relationship. Finance includes only earned outstanding partner balances and separates them from tentative estimates.

---

## 20. Register

The Register is a large-touch sales workspace intended for a tablet in the United States. It combines three controlled sources:

- Sellable winery products, prices, and stock mirrored read-only from Fatture in Cloud.
- Active hospitality packages maintained locally under Hospitality.
- Authorized manual items created in Register Admin.

The Register has four pages: **Sale**, **Inventory**, **Ledger**, and **Admin**. Completed sales are written to the local MariaDB ledger. Register sales are not posted to Fatture in Cloud in release 1.6; the future posting fields exist but remain locked off until a separate reconciliation release is approved.

### Checkout, currency, and language

1. Tap catalog items, adjust quantity or editable price, and apply any authorized line discount.
2. Select **EUR** or **USD** directly at checkout. EUR remains the accounting and VAT reporting base.
3. Select **English** or **Italiano**. This selection controls the PayPal checkout locale and the printed receipt language.
4. Confirm the active PayPal Business account. EUR prefers the Italian account when configured; USD prefers the US account. An authorized operator may select the other configured account.
5. Complete payment by cash, hosted PayPal/card checkout, or operator-confirmed PayPal Tap to Pay.

For every transaction the database preserves the subtotal, discount, VAT, and total in EUR; the actual tender currency and amount; the exact saved USD-per-EUR rate; the selected PayPal account; the checkout language; the payment or capture reference; and the operator identity. The receipt and CSV export carry the same reconciliation fields.

The ECB rate refresh is a convenient reference rate, not a claim that it is a bank settlement rate. Administrators may save the actual checkout rate when required; the saved rate remains attached to the sale even after the current setting changes.

### PayPal account setup

Protected Home Assistant App Configuration holds credentials for both accounts:

- **US PayPal Business:** the existing PayPal client ID and secret.
- **Italian PayPal Business:** the Italian PayPal client ID and secret.
- **Environment:** Sandbox for testing or Live for real payments.

The browser receives only the selected public client ID. Client secrets remain server-side. Never enter, store, or transmit raw card numbers through the Baiamonte application.

### Tap to Pay and receipts

PayPal Tap to Pay runs in the PayPal POS application on an NFC-capable phone. After PayPal approves the exact amount, the operator records the PayPal transaction reference in the Register. This is explicitly an operator confirmation; the web browser does not pretend to verify the contactless charge in real time.

The system receipt can be printed through the browser's configured system printer. It is labeled as an operational, non-fiscal receipt. The monthly Ledger shows both collected tender and EUR base values and exports a UTF-8 CSV for reconciliation.

## 21. Scheduled processes and recovery

| Process | Typical interval | Function |
|---|---:|---|
| Complete refresh | 60 min | Recovers missing or overdue subsystems |
| Planning | 15 min | Syncs Baiamonte Calendar and Tasks |
| Weather | 15 min | Imports on-site current and historical weather |
| Forecast sources | 180 min | Refreshes ensemble, SIAS, Sentinel, and seasonal evidence |
| Harvest prediction | 90 min plus queued refreshes | Recalculates harvest readiness |
| Gmail | 15 min | Imports approved messages and attachments |
| WhatsApp | 15 min | Refreshes connection and approved catalogs |
| Finance | 360 min | Pulls read-only accounting data |
| Etna | 15 min | Updates volcanic and seismic context |
| Disease | 30 min | Updates disease and heat-stress support |
| Alerts | 5 min | Evaluates operational warnings |

The complete refresh is a recovery sweep. It does not blindly duplicate every job; it reruns subsystems that are missing or substantially overdue. Manual **Run complete update now** executes the configured subsystems immediately.

---

## 22. MCP and Codex integration

The Baiamonte MCP server is a constrained interface for Codex and approved automation.

### Connection

```toml
[mcp_servers.baiamonte]
url = "http://192.168.0.10:8100/mcp"
bearer_token_env_var = "BAIAMONTE_MCP_TOKEN"
```

The endpoint is available locally or through the VPN. It requires the bearer token for every MCP request. Unauthenticated requests are rejected.

### Tool groups

The live server exposes 23 tools:

- **Status and planning:** processing status, work plan, Apple reminder lists, Baiamonte reminders, treatment reminders.
- **Review intake:** queue review item.
- **Read models:** vineyard overview, harvest report, lab history, lab decision context, weather summary, open issues, finance overview, funding report, record search.
- **Confirmed writes:** tasks, vineyard records, lab results, lab reviews, financial documents, cash transactions, and funding-requirement updates.

MCP writes are currently enabled. Every write tool still requires explicit confirmation of the exact record. Read tools can be used for diagnosis without changing data.

### Version interpretation

Home Assistant add-on version 1.6.93 is the operator-facing release. The MCP protocol handshake may report a different server-framework version; that framework identity must not be used as the Vineyard Operations update version.

---

## 23. Security and privacy

- Keep passwords, API keys, and tokens in Home Assistant add-on configuration or environment variables.
- Never place a bearer token directly in documentation, screenshots, logs, or a repository.
- Use role-based Home Assistant accounts.
- Keep finance out of shared displays.
- Keep guest contact, dietary, accessibility, and private-event details out of shared displays and public feeds.
- Keep MCP on the local network/VPN unless a separately authenticated tunnel is deliberately configured.
- Review MCP writes before enabling them on a new client.
- Use recoverable deletion for mail and records where supported.
- Preserve original evidence and audit events.

### MCP credential rule

The Baiamonte MCP connection uses `BAIAMONTE_MCP_TOKEN`. Tokens belong in a protected environment variable or connector-secret mechanism, never inside a URL, screenshot, ticket, or documentation file. Rotate a token immediately if it is exposed.

---

## 24. Troubleshooting

### A page has no data

1. Confirm the selected year.
2. Refresh the page once.
3. Check Administration -> Processing Log.
4. Check whether the source process is enabled and recent.
5. Verify that the record is approved and assigned to the correct year/vintage.
6. Do not enter replacement zeroes for unknown data.

### A map looks stale

Refresh the page after geometry changes and reopen Atlas so the map recalculates its visible size. If parcels still appear outside Sicily or the geometry count is wrong, check the Atlas process and saved cadastral geometry before editing a block.

### An alert remains after work is done

Confirm the authoritative work record is completed, then run or wait for the Alerts process. Hiding a card does not resolve the underlying alert.

### A payment reappears

Check its payment ledger, invoice total, deposits, payment timestamps, and approval state. The current integrity audit reports no fully paid invoices reappearing.

### Hospitality does not open

Confirm the Home Assistant username is linked to an Administrator or Hospitality access profile. A title alone does not grant access unless the profile is saved. Administrators configured in protected add-on settings are also recognized before a matching People profile is created.

### Register or a PayPal account does not open

Confirm the Home Assistant username has Administrator, Register, Cashier, or Hospitality Manager access. In Register Admin, the active connection line identifies Fatture in Cloud and each configured PayPal account. If an account shows **not configured**, add that account's client ID and secret in protected App Configuration and restart the add-on. Use Sandbox until both the amount and currency have been verified end to end.

### A hospitality event is missing from the TV

Confirm the reservation is requested, confirmed, or arrived and has a future or recent start time. Cancelled, declined, completed, and no-show reservations remain in history but do not occupy the active TV schedule.

### MCP does not connect

1. Confirm VPN/local reachability to port 8100.
2. Confirm `BAIAMONTE_MCP_TOKEN` is present in the client environment.
3. Confirm the Home Assistant MCP bearer token is configured.
4. Confirm the client host is permitted.
5. Restart Codex after configuration changes.
6. Use `processing_status` as the first read-only test.

---

## 25. Release 1.6.50 operational snapshot

### Release additions

- Every television page expands its primary panels through the full usable height between the fixed header and navigation on standard 1080p and shorter 1366-by-768 displays.
- Vintage, Work Plan, camera, traffic, Enology, Weather, Etna, and Communications pages no longer leave unused lower-screen bands.
- Vintage and Work Plan include live context for current weather, next harvest, disease pressure, treatment outlook, cistern and solar resources, and estate readiness.
- The Vintage history chart grows with the available panel while preserving the complete production outlook table.

Earlier release additions remain available in Appendix A instead of being repeated in this current-release snapshot.

### Verification completed for this release

- The application and MariaDB health check passed after installation.
- Administrator Hospitality access passed; an unassigned operations account was correctly denied.
- Seed packages, database migrations, television feed, grape rows, forecast structure, and cellar tanks were verified on the running installation.
- The complete automated suite passed before publication, including Today presentation, olive forecasting, Etna/trends authority, alert lifecycle and database-authority safeguards.

Source-review items remain visible rather than being guessed. Laboratory assignments, treatment safety details, inventory receipts, and planned container sharing stay in their respective review queues until authoritative evidence resolves them.

---

## Appendix A. Complete release coverage: 1.6.0-1.6.93

The operational chapters above describe the cumulative current system. For completeness, the following appendix includes every published change recorded for the full 1.6 release series, from 1.6.0 through the current 1.6.93 release. It is generated directly from the authoritative project changelog when the manual is built, so maintenance fixes and smaller workflow changes are not omitted from the owner record.

{{RELEASE_HISTORY_1_6}}

---

## 26. Glossary

**Actual:** A completed, confirmed event or measurement.  
**Evidence:** The source message, document, sensor, note, or record supporting a value.  
**GDD:** Growing degree days, a temperature accumulation measure.  
**Ingress:** Home Assistant's authenticated route into an add-on interface.  
**Intelligence proposal:** A traceable calculated result that remains separate from an approved fact.

**Pipeline:** The ordered evidence, calculation, review, approval, and refresh path for a domain decision.

**Provisional:** A system result temporarily available for planning while its required human review is pending.
**Hospitality Manager:** The role responsible for guest inquiries, packages, private experiences, guest readiness, deposits, and confirmations.

**Cashier / Register user:** A limited role that can operate estate sales without receiving finance, vineyard-write, payroll, or administration access.

**EUR base:** The authoritative euro value used for VAT and management reporting even when the customer pays in USD.

**Tender amount:** The amount actually collected in the selected payment currency.
**MCP:** Model Context Protocol, the controlled interface used by Codex and approved automation.  
**NDVI / NDRE:** Satellite vegetation indices used as trend evidence.  
**Planned:** Intended but not completed or approved.  
**Review item:** A visible uncertainty that must not be guessed.  
**Vintage:** The harvest year to which grapes or wine belong, even when later work occurs in another calendar year.  
**YoY:** Year-over-year comparison.

---

## 27. Operating principle

The system is designed to be useful without pretending to know more than the evidence supports. Confirmed facts remain authoritative, forecasts remain provisional, unknowns remain visible, and sensitive actions remain under human control.
