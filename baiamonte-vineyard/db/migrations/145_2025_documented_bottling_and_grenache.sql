-- Owner-provided DDT 14/2026 documents delivery of the bottled 2025 wine.
-- It does not state the physical bottling date or source-tank volume, so those
-- facts remain explicitly unknown rather than being inferred.
ALTER TABLE bottling_runs
  ADD COLUMN IF NOT EXISTS event_date_kind ENUM('bottled','delivery') NOT NULL DEFAULT 'bottled' AFTER bottled_at,
  ADD COLUMN IF NOT EXISTS source_document_type VARCHAR(80) NULL AFTER notes,
  ADD COLUMN IF NOT EXISTS source_document_number VARCHAR(120) NULL AFTER source_document_type,
  ADD COLUMN IF NOT EXISTS source_document_date DATE NULL AFTER source_document_number,
  MODIFY source_volume_l DECIMAL(12,3) NULL,
  MODIFY process_loss_l DECIMAL(12,3) NULL;

-- T-04 contains real 2025 Grenache and must remain occupied.
UPDATE wine_lots w
JOIN estates e ON e.id=w.estate_id AND e.slug='tenuta-baiamonte'
JOIN seasons s25 ON s25.estate_id=e.id AND s25.vintage_year=2025
JOIN cellar_containers c ON c.id=w.current_container_id AND c.estate_id=e.id AND c.code='T-04'
SET w.season_id=s25.id,
    w.code='2025-GRN-C01',
    w.name='2025 Grenache - T-04',
    w.variety_summary='Grenache',
    w.stage='aging',
    w.volume_l=225,
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Owner correction 2026-09-03: T-04 Grenache is 2025 vintage and remains in tank.')
WHERE w.id='ddca596d-e66e-4c05-a464-2aff1bfd5e54';

INSERT INTO bottling_runs
  (id,estate_id,season_id,run_code,bottled_at,event_date_kind,wine_name,legal_lot_code,denomination,origin_country,alcohol_pct,bottle_size_ml,bottles_produced,bottled_volume_l,source_volume_l,process_loss_l,bottles_per_case,cases_produced,status,legal_review_status,recorded_by,notes,source_document_type,source_document_number,source_document_date,completed_at)
SELECT '199a25e6-7a40-4acb-9d9e-2b049edd8c10',e.id,s.id,'DDT-14-2026-LRB25','2026-08-20','delivery','Vino rosso generico','LRB25','Vino rosso generico','Italia',13.0,750,2916,2187.000,NULL,NULL,6,486,'completed','approved','owner-document-2026-09-03',
       'Documentary delivery record for 2025 vintage. The delivery date is known; bottling date, source volume, remaining inventory and process loss are not stated and are not inferred. Contains sulfites. Five pallets.',
       'DDT','14/2026','2026-08-20',NOW(6)
FROM estates e JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2025
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE bottles_produced=VALUES(bottles_produced),bottled_volume_l=VALUES(bottled_volume_l),alcohol_pct=VALUES(alcohol_pct),event_date_kind='delivery',notes=VALUES(notes),source_document_type='DDT',source_document_number='14/2026',source_document_date='2026-08-20';

INSERT INTO bottling_runs
  (id,estate_id,season_id,run_code,bottled_at,event_date_kind,wine_name,legal_lot_code,denomination,origin_country,alcohol_pct,bottle_size_ml,bottles_produced,bottled_volume_l,source_volume_l,process_loss_l,bottles_per_case,cases_produced,status,legal_review_status,recorded_by,notes,source_document_type,source_document_number,source_document_date,completed_at)
SELECT '3063b8d9-ea30-4809-a9fa-f2a3186b1acb',e.id,s.id,'DDT-14-2026-LBB25','2026-08-20','delivery','Vino bianco generico','LBB25','Vino bianco generico','Italia',11.5,750,1176,882.000,NULL,NULL,6,192,'completed','approved','owner-document-2026-09-03',
       'Documentary delivery record for 2025 vintage. The delivery date is known; bottling date, source volume, remaining inventory and process loss are not stated and are not inferred. Contains sulfites. Two pallets.',
       'DDT','14/2026','2026-08-20',NOW(6)
FROM estates e JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2025
WHERE e.slug='tenuta-baiamonte'
ON DUPLICATE KEY UPDATE bottles_produced=VALUES(bottles_produced),bottled_volume_l=VALUES(bottled_volume_l),alcohol_pct=VALUES(alcohol_pct),event_date_kind='delivery',notes=VALUES(notes),source_document_type='DDT',source_document_number='14/2026',source_document_date='2026-08-20';

UPDATE historical_bottling_summaries h
JOIN estates e ON e.id=h.estate_id AND e.slug='tenuta-baiamonte'
SET h.bottle_equivalents_750ml=4092,
    h.completion_status='bottled_complete',
    h.evidence_note='Owner-provided DDT 14/2026 dated 2026-08-20: 2,916 red LRB25 bottles plus 1,176 white LBB25 bottles, all 750 ml (4,092 total; 3,069 L bottled). Separate 225 L 2025 Grenache remains aging in T-04. The prior 3,998 L wine total is retained; unbottled/process disposition beyond T-04 is not documented by this DDT.'
WHERE h.vintage_year=2025;

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'owner-document-2026-09-03','correct_vintage','wine_lot','ddca596d-e66e-4c05-a464-2aff1bfd5e54',
       JSON_OBJECT('container','T-04','vintage_year',2025,'volume_l',225,'status','aging','source','owner correction')
FROM estates e WHERE e.slug='tenuta-baiamonte'
AND NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='owner-document-2026-09-03' AND a.action='correct_vintage' AND a.entity_id='ddca596d-e66e-4c05-a464-2aff1bfd5e54');

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'owner-document-2026-09-03','document_bottling','bottling_run','199a25e6-7a40-4acb-9d9e-2b049edd8c10',
       JSON_OBJECT('vintage_year',2025,'legal_lot_code','LRB25','bottles',2916,'bottle_size_ml',750,'source_document','DDT 14/2026')
FROM estates e WHERE e.slug='tenuta-baiamonte'
AND NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='owner-document-2026-09-03' AND a.action='document_bottling' AND a.entity_id='199a25e6-7a40-4acb-9d9e-2b049edd8c10');

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'owner-document-2026-09-03','document_bottling','bottling_run','3063b8d9-ea30-4809-a9fa-f2a3186b1acb',
       JSON_OBJECT('vintage_year',2025,'legal_lot_code','LBB25','bottles',1176,'bottle_size_ml',750,'source_document','DDT 14/2026')
FROM estates e WHERE e.slug='tenuta-baiamonte'
AND NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='owner-document-2026-09-03' AND a.action='document_bottling' AND a.entity_id='3063b8d9-ea30-4809-a9fa-f2a3186b1acb');
