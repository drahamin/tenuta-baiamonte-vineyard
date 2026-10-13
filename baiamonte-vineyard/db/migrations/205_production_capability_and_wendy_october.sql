-- Expose documentary production ceilings separately from physical production
-- capability, and extend Wendy's 2026 chronology through 10 October. Source
-- documents are evidence only: they do not authorize cellar actions or prove
-- live SIAN eligibility.

CREATE TABLE IF NOT EXISTS production_capacity_references (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year INT NOT NULL,
  scenario_code VARCHAR(80) NOT NULL,
  scenario_label VARCHAR(190) NOT NULL,
  denomination VARCHAR(120) NOT NULL,
  eligibility_status VARCHAR(80) NOT NULL,
  grapes_kg DECIMAL(14,3) NOT NULL,
  wine_l DECIMAL(14,3) NOT NULL,
  full_bottles_750ml INT NOT NULL,
  source_name VARCHAR(255) NOT NULL,
  caveat TEXT NOT NULL,
  display_order INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_production_capacity_scenario (estate_id,vintage_year,scenario_code),
  CONSTRAINT fk_production_capacity_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO production_capacity_references
  (id,estate_id,vintage_year,scenario_code,scenario_label,denomination,eligibility_status,grapes_kg,wine_l,full_bottles_750ml,source_name,caveat,display_order)
SELECT UUID(),e.id,2026,x.scenario_code,x.scenario_label,x.denomination,x.eligibility_status,
       x.grapes_kg,x.wine_l,x.full_bottles,x.source_name,x.caveat,x.display_order
FROM estates e
JOIN (
  SELECT 'latest-sheet-doc' scenario_code,'Latest sheet · 93 m² eligibility shown' scenario_label,'Sicilia DOC' denomination,
         'document_evidence_only' eligibility_status,114.900 grapes_kg,80.430 wine_l,106 full_bottles,
         'Tenuta Baiamonte — Grape, Wine and Bottle Quantities · 6 October 2026' source_name,
         'Only parcel 77 / 93 m² is shown eligible in the supplied sheet. This is not a live SIAN verification or confirmed 2026 entitlement.' caveat,10 display_order
  UNION ALL SELECT 'latest-sheet-igt','Latest sheet · 93 m² eligibility shown','Terre Siciliane IGT','document_evidence_only',155.400,124.320,164,
         'Tenuta Baiamonte — Grape, Wine and Bottle Quantities · 6 October 2026',
         'Alternative to the DOC calculation, not additive. This is not a live SIAN verification or confirmed 2026 entitlement.',20
  UNION ALL SELECT 'full-listed-doc-conditional','All listed 5,461 m² · conditional','Sicilia DOC','conditional_unverified',6737.500,4716.250,6287,
         'Tenuta Baiamonte — Grape, Wine and Bottle Quantities · 6 October 2026',
         'Conditional on denomination eligibility for the full listed vineyard. Purchased fruit is excluded. The report identifies unresolved area discrepancies.',30
  UNION ALL SELECT 'full-listed-igt-conditional','All listed 5,461 m² · conditional','Terre Siciliane IGT','conditional_unverified',9106.200,7284.960,9712,
         'Tenuta Baiamonte — Grape, Wine and Bottle Quantities · 6 October 2026',
         'Alternative to the DOC calculation, not additive. Conditional on validated eligibility; purchased fruit is excluded.',40
  UNION ALL SELECT 'grecanico-superiore-conditional','Grecanico Superiore · separate option','Sicilia DOC Grecanico Superiore','conditional_unverified',1843.000,1290.100,1720,
         'Tenuta Baiamonte — Grape, Wine and Bottle Quantities · 6 October 2026',
         'Separate lower-yield option that replaces ordinary Grecanico in the DOC scenario; it is not an additional allowance.',50
) x;

-- The physical purchased-fruit vessel is Tank 39. Keep 1,078 kg as the
-- owner-confirmed intake. The notebook also says 61 crates, 1,164.95 kg gross
-- and 1.4 kg tare per crate; that arithmetic gives 1,079.55 kg, so the stated
-- tare factor and net total remain an explicit 1.55 kg reconciliation issue.
UPDATE cellar_containers
SET code='T-39',name='Tank 39 · Purchased Grenache 2026',material='stainless steel',
    location='Raiti Emanuela host cellar',
    notes='Physical Tank 39 shown in the supplied cellar photograph. Nominal 1,000 L capacity; owner-reported full occupancy on 5 October contained destemmed grapes, skins and must, not 1,000 L of measured liquid. Purchased-fruit source wording remains pending documentary confirmation.'
WHERE id='20200000-0000-4000-8000-000000000001' OR code='T-GRN-PUR-1000';

UPDATE harvest_lots
SET gross_kg=1164.950,tare_kg=86.950,crate_count=61,avg_crate_kg=ROUND(1078.000/61,2),
    winery_weight_notes='Wendy notebook: 61 crates, 1,164.95 kg gross and stated 1.4 kg empty-crate tare; owner-confirmed canonical net intake remains 1,078.00 kg. Gross minus 61 x 1.4 kg equals 1,079.55 kg, a 1.55 kg discrepancy. Stored total tare 86.95 kg is the balancing gross-to-canonical-net difference, not a claim that every crate weighed 1.4254 kg.',
    status='reconciled',
    destination='Tank 39 · Raiti Emanuela host cellar'
WHERE id='20200000-0000-4000-8000-000000000003' OR lot_code='2026-GRN-PUR-01';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.stage='fermentation',w.lot_status='active',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Wendy update through 10 October: physical vessel is Tank 39. Babo/temp were 21.2/9 C at 10:02 on 5 October and 17/22 C on 10 October, demonstrating fermentation progress. The amount removed for headspace, inoculation details and measured liquid volume were not supplied and remain pending.')
WHERE w.code='GRN-2026-02' AND COALESCE(w.notes,'') NOT LIKE '%Wendy update through 10 October%';

UPDATE cellar_control_profiles cp
JOIN cellar_containers c ON c.id=cp.container_id AND c.code='T-39'
SET cp.manual_contents='Purchased Grenache 2026 — fermenting must with skins',cp.manual_stage='fermentation',
    cp.manual_temp_c=22,cp.manual_babo=17,cp.manual_reading_at='2026-10-10 00:00:00',
    cp.manual_updated_at='2026-10-10 00:00:00',cp.updated_by='Wendy Harvest 2026 notes · supplied 2026-10-13';

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,'T-09','fermentation',x.temp_c,x.babo,x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '20500000-0000-4000-8000-000000000001' id,'wendy-current-nm-1001-0830' source_id,'2026-10-01 08:30:00' observed_at,19 temp_c,4.25 babo,'Wendy note: Nerello Tank #5 morning pump-over, Babo 4.25 and 19 C. The source says a.m. but gives no exact time; 08:30 is approximate.' note,'wendy_current_note_approx_time' status
  UNION ALL SELECT '20500000-0000-4000-8000-000000000002','wendy-current-nm-1001-evening','2026-10-01 19:00:00',NULL,NULL,'Wendy note: Nerello evening pump-over. No Babo or temperature supplied; 19:00 is approximate.','wendy_current_note_approx_time'
  UNION ALL SELECT '20500000-0000-4000-8000-000000000003','wendy-current-nm-1003-morning','2026-10-03 09:00:00',20,1.25,'Wendy note: Nerello morning reading, Babo 1.25 and 20 C. Exact time not supplied; 09:00 is approximate.','wendy_current_note_approx_time'
  UNION ALL SELECT '20500000-0000-4000-8000-000000000004','wendy-current-nm-1004-1017','2026-10-04 10:17:00',19,0.25,'Wendy note: Nerello morning pump-over at 10:17, Babo 0.25 and 19 C. Destination tanks after pressing were blank and remain unrecorded.','wendy_current_note'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),
  temp_c=VALUES(temp_c),babo=VALUES(babo),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,'T-39','fermentation',x.temp_c,x.babo,x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '20500000-0000-4000-8000-000000000011' id,'wendy-current-grn-purchased-1005-1002' source_id,'2026-10-05 10:02:00' observed_at,9 temp_c,21.2 babo,'Wendy notebook: purchased Grenache in physical Tank 39 at 10:02, Babo 21.2 and 9 C.' note,'wendy_current_note' status
  UNION ALL SELECT '20500000-0000-4000-8000-000000000012','wendy-current-grn-purchased-1010','2026-10-10 00:00:00',22,17,'Wendy note: purchased Grenache in Tank 39 on 10 October, Babo 17 and 22 C; exact time not supplied. Fermentation is active.','wendy_current_note_date_only'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-02'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),
  temp_c=VALUES(temp_c),babo=VALUES(babo),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT x.id,s.estate_id,s.id,w.id,w.current_container_id,x.operation_at,'Pump-over',x.notes
FROM seasons s
JOIN (
  SELECT '20500000-0000-4000-8000-000000000021' id,'2026-10-01 08:30:00' operation_at,'Nerello morning pump-over; source gives a.m. only, 08:30 is approximate.' notes
  UNION ALL SELECT '20500000-0000-4000-8000-000000000022','2026-10-01 19:00:00','Nerello evening pump-over; exact time not supplied, 19:00 is approximate.'
  UNION ALL SELECT '20500000-0000-4000-8000-000000000023','2026-10-04 10:17:00','Nerello morning pump-over at 10:17. Subsequent press destination tanks were blank in Wendy''s source and are not inferred.'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE container_id=VALUES(container_id),operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

UPDATE tasks
SET title='Reconcile Tank 39 headspace and fermentation start',status='in_progress',priority='normal',due_date='2026-10-14',
    notes='Tank 39 fermentation is active (Babo 21.2 / 9 C on 5 October; Babo 17 / 22 C on 10 October). Record the amount removed for headspace, final occupancy or measured liquid volume, inoculation/adjustment details and exact fermentation start. Do not infer these from the Babo decline.'
WHERE id='20200000-0000-4000-8000-000000000011';

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '20500000-0000-4000-8000-000000000031',s.estate_id,'2026-10-13 00:00:00',
       'Wendy Harvest 2026 chronology — October reconciliation',
       'Wendy chronology supplied 13 October extends Nerello readings and pump-overs through 4 October and purchased Grenache Tank 39 readings through 10 October. The purchased Grenache notebook states 61 crates, 1,164.95 kg gross, 1.4 kg empty-crate tare and 1,078 kg net. Gross less the stated crate tare is 1,079.55 kg, so the owner-confirmed 1,078 kg canonical intake is retained with a visible 1.55 kg discrepancy. No headspace-removal amount, inoculation details, measured liquid volume or Nerello press destination tanks were supplied.',
       JSON_ARRAY('wendy','harvest','2026','october','reconciliation','source-note'),
       'season',s.id
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-205','reconcile_wendy_october_and_capacity','season','2026',
       JSON_OBJECT('purchased_grenache_canonical_kg',1078,'purchased_grenache_gross_kg',1164.95,
                   'crate_count',61,'stated_empty_crate_kg',1.4,'arithmetic_net_kg',1079.55,
                   'discrepancy_kg',1.55,'physical_tank','T-39','latest_babo',17,'latest_temp_c',22,
                   'legal_capacity_status','conditional_not_live_entitlement','invented_values',FALSE)
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-205' AND a.action='reconcile_wendy_october_and_capacity');
