-- Owner decision, 15 September 2026: all grape varieties are vinified
-- separately. Retain historical migrations as audit evidence, but retire the
-- active crate-mixing/blend-planning workflow for 2026 and later vintages.

CREATE TABLE IF NOT EXISTS varietal_program_settings (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  vintage_year SMALLINT NOT NULL,
  nerello_variety_name VARCHAR(120) NOT NULL DEFAULT 'Nerello Mascalese',
  grenache_variety_name VARCHAR(120) NOT NULL DEFAULT 'Grenache',
  grecanico_variety_name VARCHAR(120) NOT NULL DEFAULT 'Grecanico',
  crate_weight_kg DECIMAL(8,3) NOT NULL DEFAULT 15.000,
  expected_yield_l_per_kg DECIMAL(8,4) NOT NULL DEFAULT 0.7000,
  tank_working_fill_pct DECIMAL(7,3) NOT NULL DEFAULT 90.000,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_varietal_program_estate_vintage (estate_id,vintage_year),
  CONSTRAINT fk_varietal_program_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO varietal_program_settings
  (id,estate_id,vintage_year,nerello_variety_name,grenache_variety_name,grecanico_variety_name,crate_weight_kg,expected_yield_l_per_kg,tank_working_fill_pct,updated_by)
SELECT UUID(),b.estate_id,b.vintage_year,b.nerello_variety_name,b.grenache_variety_name,b.grecanico_variety_name,b.crate_weight_kg,b.expected_yield_l_per_kg,b.tank_working_fill_pct,'migration-156-separate-varietals'
FROM blend_program_settings b
WHERE b.vintage_year>=2026
ON DUPLICATE KEY UPDATE crate_weight_kg=VALUES(crate_weight_kg),expected_yield_l_per_kg=VALUES(expected_yield_l_per_kg),tank_working_fill_pct=VALUES(tank_working_fill_pct),updated_by=VALUES(updated_by);

INSERT IGNORE INTO varietal_program_settings (id,estate_id,vintage_year,updated_by)
SELECT UUID(),e.id,2026,'migration-156-separate-varietals' FROM estates e;

DELETE bp FROM blend_plans bp JOIN seasons s ON s.id=bp.season_id WHERE s.vintage_year>=2026;
DELETE FROM blend_program_settings WHERE vintage_year>=2026;

UPDATE grape_allocation_plans
SET blend_kg=0,blend_crates_15kg=0,varietal_kg=total_kg,varietal_crates_15kg=total_crates_15kg,
    wine_destination=CONCAT(grape_name,' · 100% varietal'),
    field_instruction=CONCAT('Pick, identify and vinify ',grape_name,' separately; do not allocate crates across varieties.'),
    source='owner separate-varietal decision'
WHERE vintage_year>=2026;

DELETE FROM wine_output_plans WHERE vintage_year>=2026;
INSERT INTO wine_output_plans
  (estate_id,vintage_year,finished_wine,composition,grape_kg,wine_l,bottles_750ml,source)
SELECT a.estate_id,a.vintage_year,a.grape_name,CONCAT('100% ',a.grape_name),a.total_kg,
       ROUND(a.total_kg*COALESCE(v.expected_yield_l_per_kg,0.7000),3),
       FLOOR(a.total_kg*COALESCE(v.expected_yield_l_per_kg,0.7000)/0.75),
       'owner separate-varietal decision'
FROM grape_allocation_plans a
LEFT JOIN varietal_program_settings v ON v.estate_id=a.estate_id AND v.vintage_year=a.vintage_year
WHERE a.vintage_year>=2026
ON DUPLICATE KEY UPDATE composition=VALUES(composition),grape_kg=VALUES(grape_kg),wine_l=VALUES(wine_l),bottles_750ml=VALUES(bottles_750ml),source=VALUES(source);

UPDATE integration_events
SET status='ignored',error_message='Retired by owner decision: all varieties are vinified separately.'
WHERE event_type IN ('blend_crate_calculator_pending','blend_crate_calculator') AND status IN ('received','failed');

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '15600000-0000-4000-8000-000000000001',s.estate_id,'2026-09-15 18:00:00',
  'Separate-varietal vinification policy',
  'Owner decision: vinify Grecanico, Grenache and Nerello Mascalese separately from the 2026 vintage forward. The system must not calculate or suggest cross-variety crate mixing. Historical records remain historical evidence.',
  JSON_ARRAY('owner-decision','enology','separate-varietals','2026'),
  'season',s.id
FROM seasons s
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

-- Mustalone M-01 is 500 L nominal and approximately 90% full before pressing.
-- 450 L is occupancy of must/skins, not pressed juice or finished-wine volume.
UPDATE cellar_control_profiles cp
JOIN cellar_containers c ON c.id=cp.container_id AND c.estate_id=cp.estate_id
SET cp.reading_mode='manual',cp.manual_contents='Grenache must with skins',cp.manual_volume_l=450.000,
    cp.manual_stage='pre-press fermentation',cp.manual_reading_at='2026-09-15 18:00:00',
    cp.manual_updated_at='2026-09-15 18:00:00',cp.updated_by='owner update 2026-09-15'
WHERE c.estate_id='00000000-0000-4000-8000-000000000001' AND c.code='M-01';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Owner update 15 September: Grenache is in the 500 L Mustalone M-01, approximately 90% full (about 450 L vessel occupancy including skins). Press planned for 16 September. Pressed juice quantity is unknown until measured after pressing; do not use 450 L as juice or finished-wine volume.')
WHERE w.estate_id=s.estate_id AND w.code='GRN-2026-01' AND w.notes NOT LIKE '%approximately 90% full%';

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,sensory_observation,owner_text,next_check_at,status)
SELECT '15600000-0000-4000-8000-000000000002',s.estate_id,w.id,'owner-2026-grenache-mustalone-occupancy','2026-09-15 18:00:00','M-01','pre-press fermentation',
  'Owner reports the 500 L Mustalone approximately 90% full: about 450 L vessel occupancy including skins. This is not pressed juice volume. Measure and record juice quantity after pressing.',
  'Owner','2026-09-16 00:00:00','owner_confirmed_volume_estimate'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),next_check_at=VALUES(next_check_at),status=VALUES(status);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT '15600000-0000-4000-8000-000000000003',s.estate_id,s.id,w.id,c.id,'2026-09-16 00:00:00','Press planned - time pending',
  'Grenache press planned for 16 September 2026. Exact time and resulting juice quantity are pending; measure the pressed juice and update the lot/tank after pressing.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
JOIN cellar_containers c ON c.estate_id=s.estate_id AND c.code='M-01'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

UPDATE enology_process_profiles p
JOIN wine_lots w ON w.id=p.wine_lot_id AND w.code='GRN-2026-01'
SET p.target_press_at=COALESCE(p.target_press_at,'2026-09-16 00:00:00'),
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),'Press date: 16 September 2026; exact time and pressed juice quantity pending.')
WHERE p.estate_id='00000000-0000-4000-8000-000000000001';

-- Reconcile two obsolete planning lots that predated the actual 2026 cellar
-- records. The five August Grecanico and two August Nerello readings precede
-- the September harvest and are therefore retained only as excluded audit
-- evidence; they are not merged into real fermentation kinetics.
INSERT INTO enology_stage_events
  (id,estate_id,wine_lot_id,stage_code,stage_status,planned_at,completed_at,notes,approved_by,updated_by,created_at,updated_at)
SELECT UUID(),old.estate_id,current_lot.id,e.stage_code,e.stage_status,e.planned_at,e.completed_at,
       CONCAT_WS('\n',NULLIF(e.notes,''),'Merged from obsolete planning lot 2026-GRC-C01 by migration 156.'),
       e.approved_by,e.updated_by,e.created_at,e.updated_at
FROM wine_lots old
JOIN wine_lots current_lot ON current_lot.season_id=old.season_id AND current_lot.code='GRC-2026-01-P'
JOIN enology_stage_events e ON e.wine_lot_id=old.id
WHERE old.code='2026-GRC-C01'
ON DUPLICATE KEY UPDATE
  stage_status=IF(enology_stage_events.stage_status='not_started',VALUES(stage_status),enology_stage_events.stage_status),
  notes=CONCAT_WS('\n',NULLIF(enology_stage_events.notes,''),VALUES(notes)),
  updated_at=GREATEST(enology_stage_events.updated_at,VALUES(updated_at));

UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01')
SET f.wine_lot_id=NULL,
    f.status='excluded_obsolete_planning_lot',
    f.sensory_observation=CONCAT_WS(' ',NULLIF(f.sensory_observation,''),'Excluded from 2026 tank history: observation predates the actual harvest and belonged to an obsolete planning lot.')
WHERE w.estate_id='00000000-0000-4000-8000-000000000001';

UPDATE cellar_operations o JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01') SET o.wine_lot_id=NULL;
UPDATE lab_samples l JOIN wine_lots w ON w.id=l.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01') SET l.wine_lot_id=NULL;
UPDATE lab_decision_notes l JOIN wine_lots w ON w.id=l.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01') SET l.wine_lot_id=NULL;
DELETE t FROM cellar_lot_trace_records t JOIN wine_lots w ON w.id=t.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01');
DELETE l FROM wine_lot_legal_profiles l JOIN wine_lots w ON w.id=l.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01');
DELETE b FROM bottling_run_sources b JOIN wine_lots w ON w.id=b.wine_lot_id AND w.code IN ('2026-GRC-C01','2026-NM-C01');
DELETE w FROM wine_lots w JOIN seasons s ON s.id=w.season_id
WHERE s.vintage_year=2026 AND w.code IN ('2026-GRC-C01','2026-NM-C01');

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '15600000-0000-4000-8000-000000000004',s.estate_id,'2026-09-16 00:01:37',
  '2026 cellar lot reconciliation',
  'Confirmed physical lots: GRC-2026-01-P (primary Grecanico), GRC-2026-01-T (Grecanico tail fraction), and GRN-2026-01 (Grenache). Obsolete planning lots 2026-GRC-C01 and 2026-NM-C01 were removed. Explicit stage progress from the obsolete Grecanico record was merged into GRC-2026-01-P. Seven August readings that predated the September harvest were excluded from fermentation history rather than misattributed.',
  JSON_ARRAY('owner-confirmed','enology','lot-reconciliation','2026'),
  'season',s.id
FROM seasons s
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);
