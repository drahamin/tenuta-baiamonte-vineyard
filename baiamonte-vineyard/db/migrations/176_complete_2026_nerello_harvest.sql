-- Owner-confirmed Nerello Mascalese harvest and first cellar operations.
-- Date-only facts use midnight as the established storage convention.

UPDATE harvest_lots h
JOIN seasons s ON s.id=h.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=h.variety_id AND LOWER(v.name) LIKE 'nerello%'
SET h.lot_code='2026-NM-01',h.harvested_at='2026-09-25 00:00:00',h.gross_kg=2389.00,
    h.tare_kg=249.40,h.weight_kg=2139.60,h.field_weight_kg=2139.60,h.winery_weight_kg=2139.60,
    h.winery_weighed_at='2026-09-25 00:00:00',
    h.winery_weight_notes='Owner-confirmed total: 2,389.00 kg gross; 172 crates x 1.45 kg = 249.40 kg tare; calculated net fruit 2,139.60 kg. Exact weighing time not supplied.',
    h.crate_count=172,h.avg_crate_kg=12.44,h.status='reconciled',
    h.notes=CONCAT_WS('\n',NULLIF(h.notes,''),'Owner confirmed harvest completed 25 September 2026. Fruit was destemmed, treated with EnartisTan Rouge, and held at 15 C overnight into 26 September. Tannin quantity and product lot were not supplied.')
WHERE h.estate_id=s.estate_id AND DATE(h.harvested_at)='2026-09-25';

INSERT INTO harvest_lots
  (id,estate_id,season_id,lot_code,variety_id,harvested_at,gross_kg,tare_kg,weight_kg,field_weight_kg,
   winery_weight_kg,winery_weighed_at,winery_weight_notes,crate_count,avg_crate_kg,status,notes)
SELECT '17600000-0000-4000-8000-000000000001',s.estate_id,s.id,'2026-NM-01',v.id,'2026-09-25 00:00:00',
       2389.00,249.40,2139.60,2139.60,2139.60,'2026-09-25 00:00:00',
       'Owner-confirmed total: 2,389.00 kg gross; 172 crates x 1.45 kg = 249.40 kg tare; calculated net fruit 2,139.60 kg. Exact weighing time not supplied.',
       172,12.44,'reconciled',
       'Owner confirmed harvest completed 25 September 2026. Fruit was destemmed, treated with EnartisTan Rouge, and held at 15 C overnight into 26 September. Tannin quantity and product lot were not supplied.'
FROM seasons s
JOIN grape_varieties v ON v.estate_id=s.estate_id AND LOWER(v.name) LIKE 'nerello%'
WHERE s.vintage_year=2026
  AND NOT EXISTS (
    SELECT 1 FROM harvest_lots h JOIN grape_varieties hv ON hv.id=h.variety_id
    WHERE h.estate_id=s.estate_id AND h.season_id=s.id AND LOWER(hv.name) LIKE 'nerello%'
      AND DATE(h.harvested_at)='2026-09-25'
  );

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,grapes_kg,cassette_count,evidence_status,reconciliation_note,
   first_pick_date,last_pick_date,harvest_date_precision,source_note_id,source_note_name)
SELECT s.estate_id,2026,'Nerello Mascalese',2139.60,172,'owner_confirmed',
       '2,389.00 kg gross less 172 crates x 1.45 kg tare (249.40 kg) = 2,139.60 kg net fruit.',
       '2026-09-25','2026-09-25','day','owner-2026-nerello-harvest','Owner update - 2026 Nerello harvest'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE grapes_kg=VALUES(grapes_kg),cassette_count=VALUES(cassette_count),
  evidence_status=VALUES(evidence_status),reconciliation_note=VALUES(reconciliation_note),
  first_pick_date=VALUES(first_pick_date),last_pick_date=VALUES(last_pick_date),
  harvest_date_precision=VALUES(harvest_date_precision),source_note_id=VALUES(source_note_id),source_note_name=VALUES(source_note_name);

UPDATE harvest_plans p
JOIN seasons s ON s.id=p.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=p.variety_id AND LOWER(v.name) LIKE 'nerello%'
SET p.status='complete',p.planned_pick_date='2026-09-25',p.approved_by='David Rahamin',p.confidence='high',
    p.forecast_method='owner confirmed actual harvest',
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),'Completed 25 September 2026: 172 crates, 2,389.00 kg gross, 249.40 kg crate tare, 2,139.60 kg net fruit.'),
    p.updated_at=NOW(6)
WHERE p.estate_id=s.estate_id;

INSERT INTO wine_lots
  (id,estate_id,season_id,code,harvest_lot_reference,name,stage,lot_status,fruit_kg,variety_summary,started_at,notes)
SELECT '17600000-0000-4000-8000-000000000002',s.estate_id,s.id,'NM-2026-01','2026-NM-01',
       'Nerello Mascalese 2026','must','active',2139.60,'Nerello Mascalese','2026-09-25 00:00:00',
       'Owner confirmed 25 September harvest: 2,139.60 kg net fruit. Destemmed, EnartisTan Rouge applied, then held at 15 C overnight. Vessel, must volume, tannin quantity and product lot remain to be recorded.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE harvest_lot_reference=VALUES(harvest_lot_reference),name=VALUES(name),stage=VALUES(stage),
  lot_status=VALUES(lot_status),fruit_kg=VALUES(fruit_kg),variety_summary=VALUES(variety_summary),
  started_at=VALUES(started_at),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,notes)
SELECT '17600000-0000-4000-8000-000000000003',s.estate_id,s.id,w.id,'2026-09-25 00:00:00','Destemming',
       'Owner-confirmed completed after the 25 September Nerello harvest; exact operation time not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,temp_c,notes)
SELECT '17600000-0000-4000-8000-000000000004',s.estate_id,s.id,w.id,'2026-09-25 00:00:00','Overnight cold hold',15.00,
       'Owner-confirmed: destemmed Nerello must was left at 15 C overnight from 25 into 26 September 2026. Exact start/end times and vessel were not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),temp_c=VALUES(temp_c),notes=VALUES(notes);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by)
SELECT '17600000-0000-4000-8000-000000000005',s.estate_id,w.id,'EnartisTan Rouge','tannin','applied',
       '2026-09-25 00:00:00',NULL,NULL,NULL,
       'Owner-confirmed addition to destemmed Nerello must before the overnight 15 C hold. Photograph confirms EnartisTan Rouge identity; quantity, product lot and exact application time were not supplied.',
       'David Rahamin','2026-09-26 00:00:00','Owner update 2026-09-26'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),
  event_status=VALUES(event_status),applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),
  product_lot=VALUES(product_lot),reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),
  approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '17600000-0000-4000-8000-000000000006',s.estate_id,'2026-09-26 00:00:00',
       '2026 Nerello harvest and first cellar operations',
       'Harvest completed 25 September: 172 crates, 2,389.00 kg gross. Empty crates are 1.45 kg each, so total tare is 249.40 kg and net fruit is 2,139.60 kg. Fruit was destemmed, EnartisTan Rouge was applied, and the must was held at 15 C overnight into 26 September. Tannin quantity, product lot, vessel and resulting must volume were not supplied and remain explicit pending fields.',
       JSON_ARRAY('owner-confirmed','harvest','nerello-mascalese','enology','2026'),'season',s.id
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-176','reconcile_harvest_and_cellar','harvest_lot','owner-2026-nerello-harvest',
       JSON_OBJECT('variety','Nerello Mascalese','harvest_date','2026-09-25','crate_count',172,
                   'gross_kg',2389.00,'crate_tare_kg',1.45,'total_tare_kg',249.40,'net_kg',2139.60,
                   'destemmed',TRUE,'tannin','EnartisTan Rouge','overnight_hold_c',15,
                   'pending',JSON_ARRAY('tannin quantity','product lot','vessel','must volume'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-176' AND a.entity_id='owner-2026-nerello-harvest');
