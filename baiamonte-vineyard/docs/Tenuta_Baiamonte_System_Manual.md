# Tenuta Baiamonte Vineyard Operations

## System Manual

**Release covered:** 1.3.25  
**Manual date:** 19 August 2026  
**System owner:** Azienda Agricola Tenuta Baiamonte S.S.  
**Operational authority:** Vineyard Operations MariaDB database

This manual describes what the Baiamonte system does, how staff use it, how its calculations and predictions work, how data moves between services, and how to recognize and recover from problems. It is written for owners, vineyard staff, cellar staff, accountants, agronomists, kiosk users, and technical administrators.

---

## 1. What the system is

Tenuta Baiamonte Vineyard Operations is a private estate-management system hosted as a Home Assistant add-on. It combines vineyard work, harvest, cellar, laboratory, weather, treatment, labor, payment, olive-oil, messaging, alert, map, and forecasting functions in one controlled interface.

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

---

## 4. First use and navigation

1. Sign in to Home Assistant with the appropriate account.
2. Open **Vineyard Operations** from the sidebar.
3. Choose the working year. Year selection changes the harvest, laboratory, weather comparison, labor, treatment, olive, and historical context.
4. Use the main sections for daily work; use Administration only for configuration or audit tasks.
5. Treat yellow or amber items as uncertain or awaiting review. Treat red items as active exceptions, not automatically as failed equipment.

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

The current system reports zero processing errors in the last 24 hours, no unhealthy processes, no failed intake items, and no blocking data-quality issues.

---

## 16. Maps, parcels, and Sentinel-2

The Atlas stores official cadastral parcels separately from operational vineyard blocks. All seven current cadastral parcels have verified polygon geometry. Operational block rows may reference combinations of parcels without duplicating the polygon in the block table.

Sentinel-2 uses direct block polygons when available. Otherwise it uses the verified cadastral parcels as an estate-geometry fallback. The dashboard must say **cadastral parcels mapped** rather than incorrectly claiming that the estate has no geometry.

Sentinel indices are trend evidence only. A vegetation change may support a field check but cannot by itself approve a treatment or choose a harvest date.

---

## 17. TV, iPad, and kiosk displays

### TV

The TV rotates read-only estate status, current work, weather, prediction, rainfall, seasonal, camera, aircraft, and vessel information. Animated “today” markers show the current point in seasonal charts. Ticker speed and cycle time are configurable.

### iPad

The `ipad` profile is a larger, finance-free operations dashboard with weather, solar, energy, lights, cameras, security, vineyard information, media, and AI links.

### Tablet labels

Tank-label devices use a dedicated enrollment flow. QR provisioning is preferred, with the full URL retained as a backup. Reprovision controls should replace the device identity cleanly rather than creating duplicate tablets.

---

## 18. Scheduled processes and recovery

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

## 19. MCP and Codex integration

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

Home Assistant add-on version 1.3.25 is the operator-facing release. The MCP protocol handshake currently reports server software version 1.29.0; this is the MCP server framework identity and must not be used as the Vineyard Operations update version.

---

## 20. Security and privacy

- Keep passwords, API keys, and tokens in Home Assistant add-on configuration or environment variables.
- Never place a bearer token directly in documentation, screenshots, logs, or a repository.
- Use role-based Home Assistant accounts.
- Keep finance out of shared displays.
- Keep MCP on the local network/VPN unless a separately authenticated tunnel is deliberately configured.
- Review MCP writes before enabling them on a new client.
- Use recoverable deletion for mail and records where supported.
- Preserve original evidence and audit events.

### Current MCP security action

The Baiamonte MCP connection correctly uses `BAIAMONTE_MCP_TOKEN`. A separate `local_mcp` Codex connection currently embeds its token in the URL. Rotate that token and move it to a protected environment-variable or connector-secret mechanism. Do not copy the existing URL into tickets or documentation.

---

## 21. Troubleshooting

### A page has no data

1. Confirm the selected year.
2. Refresh the page once.
3. Check Administration -> Processing Log.
4. Check whether the source process is enabled and recent.
5. Verify that the record is approved and assigned to the correct year/vintage.
6. Do not enter replacement zeroes for unknown data.

### A map looks stale

Refresh the page after geometry changes. The current code-review audit identifies a remaining issue where a map already opened once may not rebuild after data refresh while the Atlas tab is hidden.

### An alert remains after work is done

Confirm the authoritative work record is completed, then run or wait for the Alerts process. Hiding a card does not resolve the underlying alert.

### A payment reappears

Check its payment ledger, invoice total, deposits, payment timestamps, and approval state. The current integrity audit reports no fully paid invoices reappearing.

### MCP does not connect

1. Confirm VPN/local reachability to port 8100.
2. Confirm `BAIAMONTE_MCP_TOKEN` is present in the client environment.
3. Confirm the Home Assistant MCP bearer token is configured.
4. Confirm the client host is permitted.
5. Restart Codex after configuration changes.
6. Use `processing_status` as the first read-only test.

---

## 22. Current audit snapshot - 19 August 2026

### Healthy findings

- Add-on 1.3.25 is installed, started, and current.
- MariaDB is connected.
- Zero processing errors in the last 24 hours.
- No unhealthy scheduled processes.
- No failed intake items or unresolved integration failures.
- MCP bearer token, Mac/Codex intake, and OpenAI API are configured.
- MCP authenticated handshake and `processing_status` tool call succeeded.
- Unauthenticated MCP requests are rejected with HTTP 401.
- All 23 MCP tools are discoverable.
- Payment ledger has no paid-status, partial-status, timestamp, or reappearing-payment mismatch.
- GitHub has no open issues.

### Review items already visible in the system

- Nine laboratory reports need source review.
- Five treatment records need safety-detail review.
- One future-dated labor/reimbursement record needs review.
- One planned shared container needs confirmation; no occupied container is shared.

### GitHub review findings

GitHub notification emails are legitimate automated Codex review messages generated when pull requests are opened. Ten suggestions were found across seven vineyard pull requests.

- One suggestion - preserving the 2024 olive defaults - is resolved in 1.3.25.
- One migration-version concern is not active on the sole live installation but is a valid future migration-discipline warning.
- Eight suggestions still match current `main` and should be repaired in a dedicated release:
  1. Scope the migration-059 olive correction to the Baiamonte estate.
  2. Do not display EUR 0 as a valid cost model for unsaved olive years.
  3. Ensure a fresh database creates the authoritative 2024 olive record.
  4. Open the collapsed Communications panel when preparing an intake reply.
  5. Rebuild Atlas geometry after hidden refreshes.
  6. Mutate `updated_at` when reclaiming stale intake processing work.
  7. Do not send media-download error replies to unapproved WhatsApp senders.
  8. Restore hidden-row behavior in the compact WhatsApp contact filter.

Two old pull requests remain open: #67 and #120. Their functionality has been superseded by later main-branch work and they should be closed after a final human check, not merged into 1.3.25.

---

## 23. Glossary

**Actual:** A completed, confirmed event or measurement.  
**Evidence:** The source message, document, sensor, note, or record supporting a value.  
**GDD:** Growing degree days, a temperature accumulation measure.  
**Ingress:** Home Assistant's authenticated route into an add-on interface.  
**MCP:** Model Context Protocol, the controlled interface used by Codex and approved automation.  
**NDVI / NDRE:** Satellite vegetation indices used as trend evidence.  
**Planned:** Intended but not completed or approved.  
**Review item:** A visible uncertainty that must not be guessed.  
**Vintage:** The harvest year to which grapes or wine belong, even when later work occurs in another calendar year.  
**YoY:** Year-over-year comparison.

---

## 24. Operating principle

The system is designed to be useful without pretending to know more than the evidence supports. Confirmed facts remain authoritative, forecasts remain provisional, unknowns remain visible, and sensitive actions remain under human control.
