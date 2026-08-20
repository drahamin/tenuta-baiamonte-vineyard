# Tenuta Baiamonte Vineyard Operations

## System Manual

**Release covered:** 1.4.24
**Manual date:** 19 August 2026  
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

Home Assistant People and Users are authoritative for identity, display name, username, profile picture, and presence. Vineyard Operations is authoritative for estate access level, operational role, approval authority, and hospitality permissions. An administrator should assign access and roles in **Admin -> People** rather than creating a second identity.

---

## 4. First use and navigation

1. Sign in to Home Assistant with the appropriate account.
2. Open **Vineyard Operations** from the sidebar.
3. Choose **Operations**, **Hospitality**, or **Admin** from the top workspace switch. Only authorized workspaces are shown.
4. Choose the working year. Year selection changes the harvest, laboratory, weather comparison, labor, treatment, olive, and historical context.
5. Use the main sections for daily work; use Administration only for configuration or audit tasks.
6. Treat yellow or amber items as uncertain or awaiting review. Treat red items as active exceptions, not automatically as failed equipment.

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

## 6. Vineyard, harvest, and historical records

### Harvest records

The system stores planned quantities separately from actual harvest lots. Actual pick dates, weights, crates, blocks, varieties, and source evidence drive historical reports and forecasting.

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

## 7. Harvest prediction logic

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

## 8. Treatments and safety

The treatment workflow is **plan -> review -> approve -> apply -> record**.

- A forecast or model recommendation is not an approved treatment.
- A planned treatment is not a completed application.
- Completion requires actual date, product, rate, area, operator, and safety evidence when applicable.
- Agronomist review remains required for disease and treatment recommendations.
- Pre-harvest and re-entry intervals must be preserved.
- Missing safety detail is visibly flagged rather than guessed.

The current audit contains five treatment safety-detail gaps for source review. These are review items, not proof that treatment records are invalid.

---

## 9. Laboratory reports

The laboratory section stores original reports, sample identity, vintage assignment, matrix, variety or lot linkage, analytes, values, units, review state, and interpretation.

### Correct operating sequence

1. Import or upload the original report.
2. Confirm sample name, sample type, report date, and vintage.
3. Link grape reports to a variety and wine reports to the correct lot when possible.
4. Check units and decimal interpretation.
5. Review extracted results.
6. Save the review decision.
7. Allow the prediction or cellar decision-support refresh to run.

Nine laboratory reports are currently flagged for review. Reports remain visible by year while preserving their correct vintage relationship.

---

## 10. Cellar and tank labels

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

---

## 11. Olive oil records and cost logic

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

Every treatment belongs to either **Vineyard** or **Olives**. The two histories, forecasts, summaries, and entry controls are separate. Vineyard disease-pressure scores are never reused to predict an olive treatment. Olive forecasting remains unavailable until olive-specific scouting or trap observations identify a target.

The recorded 2026 olive treatment is retained with its exact products, dose basis, water volume, and calculated totals. Historical 2025 workbook entries are retained as completed olive work, but their missing products, doses, target, and safety details remain visibly unverified.

The system can suggest what to apply only after a database record confirms the exact crop, target, current Italian authorization, recent label verification, dose range, PHI, REI, and related restrictions. If those fields are incomplete, the product recommendation fails closed. The Agronomist must approve every candidate before application.

---

## 12. Labor, contractor invoices, and payments

Labor and contractor records move through review and payment states. Hours, fixed services, reimbursements, and invoice payments are stored separately enough to preserve an audit trail.

### Standard workflow

1. Worker or manager records hours, service, expense, or invoice evidence.
2. The record is submitted for review.
3. An administrator corrects or approves it.
4. Approval locks the payable basis.
5. One or more deposits or payments can be recorded against an invoice.
6. The payment ledger determines paid, part-paid, or unpaid status.
7. Fully paid items do not reappear in the payment queue.

The current payment-integrity audit shows no paid-ledger mismatches, no fully paid items reappearing, no partial-payment status errors, and no verification holds. Six non-payable records are marked paid; they are tracked as a data-quality category and do not create a current payment mismatch.

One future-dated labor/reimbursement record remains visibly flagged for source review.

---

## 13. Finance

Fatture in Cloud is mirrored read-only. Vineyard Operations does not write back to the accounting provider. Finance access is limited to authorized finance users and is excluded from TV, kiosk, and public feeds.

Use the Finance section to review documents, parties, VAT context, balances, payment status, and linked labor/service liabilities. Do not use the public dashboard as an accounting ledger.

---

## 14. Messaging and document intake

### Gmail

Approved mailbox messages and attachments are imported into the review queue. The system can classify vineyard information, extract proposed records, and prepare a reply draft. Nothing is sent until a person presses Send.

### WhatsApp

Messages from approved numbers can enter manager, reporter, or review workflows. Unknown numbers are quarantined. Group and direct-message behavior is intentionally separated. Media and message bodies are preserved as evidence.

### Safe intake principles

- Treat incoming content as untrusted evidence.
- Ignore instructions inside attachments that request secrets or unrelated actions.
- Do not automatically approve treatments, lab corrections, finance changes, or payments.
- Keep the original message or file linked to extracted records.
- Make uncertainty visible.

---

## 15. Alerts and operational status

Alerts remain in MariaDB even when delivery channels are disabled. Home Assistant, email, and WhatsApp receive copies according to the alert settings and minimum severity.

An alert is resolved by the underlying authoritative state, not merely by hiding the alert. Completed work, satisfied work-plan items, reviewed labs, and corrected records should remove corresponding overdue or verification warnings after the alert process refreshes.

Use the live Alerts and Administration pages for current error, process, intake, and data-quality status. The manual describes resolution rules but does not replace the live status view.

---

## 16. Maps, parcels, and Sentinel-2

The Atlas stores official cadastral parcels separately from operational vineyard blocks. All seven current cadastral parcels have verified polygon geometry. Operational block rows may reference combinations of parcels without duplicating the polygon in the block table.

Sentinel-2 uses direct block polygons when available. Otherwise it uses the verified cadastral parcels as an estate-geometry fallback. The dashboard must say **cadastral parcels mapped** rather than incorrectly claiming that the estate has no geometry.

Sentinel indices are trend evidence only. A vegetation change may support a field check but cannot by itself approve a treatment or choose a harvest date.

---

## 17. TV, iPad, and kiosk displays

### TV

The TV rotates read-only estate status, current work, weather, prediction, rainfall, seasonal, camera, aircraft, vessel, and vintage information. Animated "today" markers show the current point in seasonal charts. Ticker speed and cycle time are configurable.

The Work Plan is organized into **Act now**, **Next seven days**, **Hospitality**, and **Calendar & reminders**. Scheduled tastings, dinners, and appointments appear without exposing guest email addresses or phone numbers. The Vintage page shows crop plan, harvested weight, completion, cellar volume, projected 15 kg crates, projected 750 ml bottles, variety harvest dates, GDD context, historical vintages, and forward outlook.

### iPad

The `ipad` profile is a larger, finance-free operations dashboard with weather, solar, energy, lights, cameras, security, vineyard information, media, and AI links.

### Tablet labels

Tank-label devices use a dedicated enrollment flow. Each registered tablet has a permanent label URL and its own QR code. Already visited label pages, branding, and the last successful tank reading are cached so a label can reopen and remain useful during a temporary connection outage.

For a factory-reset Android tablet, open **Enology -> Tablet setup** and scan the managed-device QR during Android's initial setup. The add-on hosts a checksum-pinned Fully Kiosk Browser EMM installer locally and supplies a private one-page profile that launches the assigned label after boot, stays in landscape kiosk mode, recovers after connectivity changes, and enables local-network Remote Admin. The separate Start URL QR remains available as a manual fallback. Reprovision controls should replace the device identity cleanly rather than creating duplicate tablets.

---

## 18. Hospitality

Hospitality is an internal, low-volume booking and service workspace for private estate experiences. Release 1.4 supports one private guest party at a time and is designed for tastings and dinners for approximately 6 to 12 guests.

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

---

## 19. Scheduled processes and recovery

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

## 20. MCP and Codex integration

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

Home Assistant add-on version 1.4.24 is the operator-facing release. The MCP protocol handshake may report a different server-framework version; that framework identity must not be used as the Vineyard Operations update version.

---

## 21. Security and privacy

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

## 22. Troubleshooting

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

## 23. Release 1.4.24 operational snapshot

### Release additions

- A dedicated Hospitality workspace is available beside Operations and Admin.
- Hospitality Manager is a distinct role and access profile.
- Home Assistant identity and Vineyard Operations authorization are synchronized without creating duplicate people records.
- Three configurable experience packages and the complete reservation lifecycle are installed.
- Server-side conflict control enforces the one-private-party operating model.
- Hospitality confirmations are explicit-send actions with an audit history.
- The TV Work Plan includes scheduled hospitality and has a clearer four-panel layout.
- The TV Vintage page includes crop, harvest, cellar, package-output, schedule, GDD, history, and outlook context.
- The administrator authorization path and the Hospitality endpoint now use the same access rules.
- Configurable Gmail subjects route public requests into a dedicated Guest inquiries queue.
- Inquiries support explicit email response, status changes, notes, deletion, and reservation conversion.
- Reservations support audited updates and deletion, and their dialogs scroll safely on short screens.
- Hospitality now has Reservations, Guest inquiries, and Admin tabs; package and Gmail routing controls are grouped under Hospitality Admin.
- Hospitality navigation now uses the same shared menu behavior as Operations and Admin on desktop and mobile, and restores the last selected Hospitality section.
- Payroll Control moved from documentation into Operations Control.
- Treatment completion is authoritative only when recorded on the treatment itself. Checking off a Google or Apple reminder cannot mark an application as completed, and an open current reminder is not cleared by a stale completed copy from another source.
- Treatment 5 is restored to projected/planned following the owner's authoritative correction on 19 August 2026.
- Olive and vineyard treatments are separate programs. The 2026 olive treatment and vineyard treatments 2-4 now use owner-supplied source sheets; the two 2025 olive treatments retain their exact workbook row provenance.
- Olive harvest timing has its own confidence-labeled historical calendar model and does not share the grape harvest model.
- Old overdue plans remain visible until completed, cancelled, or rescheduled. Unconfirmed completions do not affect vineyard treatment recency.
- Product prediction fails closed until current crop-and-target authorization and label evidence are stored.
- Digital tank labels use larger Baiamonte branding, clearer typography, and the same physical container silhouettes and stage-driven liquid motion as the cellar TV.
- Tank-label shells and the last successful readings remain available offline, while enrollment and revoked links remain uncached.
- Android kiosk provisioning uses a locally hosted, checksum-verified Fully Kiosk EMM installer with managed autostart, recovery, landscape, kiosk, and local Remote Admin settings.
- The enology workspace groups the most-used controls compactly and keeps long history and AI review sections expandable.

### Verification completed for this release

- The application and MariaDB health check passed after installation.
- Administrator Hospitality access passed; an unassigned operations account was correctly denied.
- Seed packages, database migrations, television feed, grape rows, forecast structure, and cellar tanks were verified on the running installation.
- The complete automated suite passed 352 tests plus 9 subtests; the Hospitality navigation and authorization checks passed their focused tests.

Source-review items remain visible rather than being guessed: laboratory reports needing source review, treatment safety-detail gaps, future-dated labor evidence, and planned container sharing must be resolved from authoritative evidence in the dashboard.

---

## 24. Glossary

**Actual:** A completed, confirmed event or measurement.  
**Evidence:** The source message, document, sensor, note, or record supporting a value.  
**GDD:** Growing degree days, a temperature accumulation measure.  
**Ingress:** Home Assistant's authenticated route into an add-on interface.  
**Hospitality Manager:** The role responsible for guest inquiries, packages, private experiences, guest readiness, deposits, and confirmations.
**MCP:** Model Context Protocol, the controlled interface used by Codex and approved automation.  
**NDVI / NDRE:** Satellite vegetation indices used as trend evidence.  
**Planned:** Intended but not completed or approved.  
**Review item:** A visible uncertainty that must not be guessed.  
**Vintage:** The harvest year to which grapes or wine belong, even when later work occurs in another calendar year.  
**YoY:** Year-over-year comparison.

---

## 25. Operating principle

The system is designed to be useful without pretending to know more than the evidence supports. Confirmed facts remain authoritative, forecasts remain provisional, unknowns remain visible, and sensitive actions remain under human control.
