-- Wendy's 2026 harvest/cellar note and notebook photo, supplied 2026-09-15.
-- Exact source facts are retained; date-only observations use midnight only as a
-- storage convention and say explicitly that the source did not record a time.

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '15500000-0000-4000-8000-000000000001',s.estate_id,'2026-09-15 21:30:00',
  'Wendy - Harvest 2026 Grecanico and Grenache cellar notes',
  'Crates empty weight: 1.45 kg.\n\nGRECANICO\nPicked 9 September 2026. 199 crates. Notebook gross weight of all crates: 2,588.08 kg. Notebook also states "60% must 769.68"; its calculation basis is not defined. Soft press at 1.8 bar on 10 September. Six people, 06:30-14:00. Cooling truck; take to Raiti.\n\n11 September: take samples from Tank #3 and small Tank #44. Green bottle: catechins. Panna bottle: catechins and NTU. ES181 preparation: 5 L water at 35 C, 500 g yeast, mix and rest 20 minutes, add a glass of Grecanico from the tank to equalize temperature, then add. First rack instruction: clean empty Tank #5; open the top of Tank #3; pump Tank #3 to Tank #5; discard the last material at the bottom of Tank #3; rinse Tank #3 with water; open Tank #5 at the top and rack back to Tank #3. Repeat catechin green-bottle and catechin/NTU panna-bottle testing.\n\nGrecanico readings: 12 September Tank #44 Babo 16, 22 C; Tank #3 Babo 17.4, temperature not recorded. 13 September Tank #3 Babo 19, 15 C; Tank #44 Babo 15, 25 C. At 12:35 Tank #3 Babo 16.9, 15 C; Tank #44 Babo 11.8, 25 C. 15 September owner update: small white Tank #44 Babo 2.2, 26 C; big white Tank #3 (system T-06) Babo 12.2, 18 C.\n\nGRENACHE\nPicked 10 September 2026. Four people, 06:30-09:00. 35 crates. Notebook gross weight: 450 kg. Yeast instruction: 5 L water, one spoon sugar, 180 yeast (unit and product not stated); mix and cool. Must temperature 25 C; combine when yeast mixture is 25 C; add to must by digging one hole on each side and cover the must.\n\nPunch-down program: three times per day, one full circuit, morning/noon/evening. 11 September noon Babo 12.4, 26 C; evening Babo 12, 25 C. 12 September 09:39 Babo 8, 27 C; 12:14 punch down; 18:34 Babo 4.3, 27 C. 13 September 09:05 Babo 3, 27 C.',
  JSON_ARRAY('wendy','harvest','2026','grecanico','grenache','cellar','source-note'),
  'season',s.id
FROM seasons s
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

-- Reconcile the photographed/notebook gross weights against the explicit crate tare.
UPDATE harvest_lots h
JOIN seasons s ON s.id=h.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=h.variety_id AND v.name='Grecanico'
SET h.gross_kg=2588.08,h.tare_kg=288.55,h.weight_kg=2299.53,h.winery_weight_kg=2299.53,
    h.winery_weighed_at='2026-09-09 14:00:00',
    h.winery_weight_notes='Wendy notebook photo: 2,588.08 kg gross; 199 crates x 1.45 kg = 288.55 kg tare; calculated net 2,299.53 kg.',
    h.crate_count=199,h.avg_crate_kg=11.56,h.destination='Raiti winery; transported by cooling truck',h.status='reconciled'
WHERE h.estate_id=s.estate_id AND DATE(h.harvested_at)='2026-09-09';

UPDATE harvest_lots h
JOIN seasons s ON s.id=h.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=h.variety_id AND v.name='Grenache'
SET h.gross_kg=450.00,h.tare_kg=50.75,h.weight_kg=399.25,h.winery_weight_kg=399.25,
    h.winery_weighed_at='2026-09-10 09:00:00',
    h.winery_weight_notes='Wendy note: 450.00 kg gross; 35 crates x 1.45 kg = 50.75 kg tare; calculated net 399.25 kg.',
    h.crate_count=35,h.avg_crate_kg=11.41,h.destination='Raiti winery',h.status='reconciled'
WHERE h.estate_id=s.estate_id AND DATE(h.harvested_at)='2026-09-10';

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,grapes_kg,cassette_count,evidence_status,reconciliation_note,first_pick_date,last_pick_date,harvest_date_precision,source_note_id,source_note_name)
VALUES
  ('00000000-0000-4000-8000-000000000001',2026,'Grecanico',2299.53,199,'wendy_source_note','Notebook gross 2,588.08 kg less 199 crates x 1.45 kg tare = 2,299.53 kg net. "60% must 769.68" retained in the source note without interpreting its basis.','2026-09-09','2026-09-09','day','wendy-harvest-2026','Wendy - Harvest 2026'),
  ('00000000-0000-4000-8000-000000000001',2026,'Grenache',399.25,35,'wendy_source_note','Notebook gross 450.00 kg less 35 crates x 1.45 kg tare = 399.25 kg net.','2026-09-10','2026-09-10','day','wendy-harvest-2026','Wendy - Harvest 2026')
ON DUPLICATE KEY UPDATE grapes_kg=VALUES(grapes_kg),cassette_count=VALUES(cassette_count),evidence_status=VALUES(evidence_status),reconciliation_note=VALUES(reconciliation_note),first_pick_date=VALUES(first_pick_date),last_pick_date=VALUES(last_pick_date),harvest_date_precision=VALUES(harvest_date_precision),source_note_id=VALUES(source_note_id),source_note_name=VALUES(source_note_name);

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,quantity_value,quantity_unit,details,evidence_status,canonical_table,canonical_key,conflict_note)
VALUES
  ('15500000-0000-4000-8000-000000000011','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','crate-tare','2026-09-09',2026,'day','harvest','Empty crate tare',1.45,'kg/crate','Empty crate weight is 1.45 kg.','user_source_note',NULL,NULL,NULL),
  ('15500000-0000-4000-8000-000000000012','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','grecanico-harvest','2026-09-09',2026,'day','harvest','Grecanico',2299.53,'net kg','199 crates; notebook gross 2,588.08 kg; tare 288.55 kg; calculated net 2,299.53 kg. Six people 06:30-14:00; cooling truck to Raiti.','user_source_note','vintage_summaries','2026:Grecanico','The note separately states "60% must 769.68" without defining its basis.'),
  ('15500000-0000-4000-8000-000000000013','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','grecanico-soft-press','2026-09-10',2026,'day','cellar','Grecanico soft press',1.8,'bar','Soft pressed at 1.8 bar.','user_source_note','cellar_operations','wendy-2026-grecanico-soft-press',NULL),
  ('15500000-0000-4000-8000-000000000014','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','grecanico-cellar-instructions','2026-09-11',2026,'day','cellar','Grecanico Tank #3 and Tank #44',NULL,NULL,'Samples requested for catechins (green bottle) and catechins plus NTU (panna bottle). ES181: 5 L water at 35 C, 500 g yeast, rest 20 minutes and temper with a glass of Tank #3 must. First-rack sequence Tank #3 to clean/open Tank #5, discard bottom sediment, rinse Tank #3, then open Tank #5 and rack back.','user_source_note',NULL,NULL,'Instructions are retained as source evidence; the note does not explicitly confirm every step as completed.'),
  ('15500000-0000-4000-8000-000000000015','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','grenache-harvest','2026-09-10',2026,'day','harvest','Grenache',399.25,'net kg','35 crates; notebook gross 450.00 kg; tare 50.75 kg; calculated net 399.25 kg. Four people 06:30-09:00.','user_source_note','vintage_summaries','2026:Grenache',NULL),
  ('15500000-0000-4000-8000-000000000016','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','grenache-fermentation','2026-09-11',2026,'day','cellar','Grenache fermentation',NULL,NULL,'Yeast preparation: 5 L water, one spoon sugar and quantity 180 yeast; product and unit not stated. Cool to the 25 C must temperature, add into holes on two sides and cover. Punch down three times daily, one full circuit.','user_source_note',NULL,NULL,'Product identity and the unit for 180 were not stated and are not inferred.'),
  ('15500000-0000-4000-8000-000000000017','00000000-0000-4000-8000-000000000001','wendy-harvest-2026','Wendy - Harvest 2026','fermentation-readings','2026-09-13',2026,'day','cellar','2026 fermentation readings',NULL,NULL,'All Grecanico and Grenache Babo/temperature readings from 11-13 September are stored as fermentation observations linked to their exact wine lots.','user_source_note','fermentation_observations','wendy-harvest-2026-readings',NULL)
ON DUPLICATE KEY UPDATE fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),quantity_value=VALUES(quantity_value),quantity_unit=VALUES(quantity_unit),details=VALUES(details),evidence_status=VALUES(evidence_status),canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key),conflict_note=VALUES(conflict_note);

-- Keep the current lot identities/assignments and correct stale notes.
UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.stage='fermentation',w.fruit_kg=2299.53,w.harvest_lot_reference='Wendy Harvest 2026 - Grecanico 9 Sep',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Wendy 2026 harvest note: Grecanico 2,299.53 kg net from 2,588.08 kg gross and 288.55 kg crate tare; soft pressed 10 September at 1.8 bar. "60% must 769.68" is retained without interpreting its basis.')
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-P' AND w.notes NOT LIKE '%Wendy 2026 harvest note:%';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.stage='fermentation',w.volume_l=225.00,
    w.notes='Tail/press-fraction Grecanico fermentation in physical Tank No. 44, nominal capacity 300 L. Owner reported approximately three-quarters full on 15 September 2026, giving an estimated working volume of 225 L. Wendy readings from 12-13 September are linked to this lot. Measure actual volume before exact dosing.'
WHERE w.estate_id=s.estate_id AND w.code='GRC-2026-01-T';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.stage='fermentation',w.fruit_kg=399.25,w.harvest_lot_reference='Wendy Harvest 2026 - Grenache 10 Sep',
    w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Wendy 2026 harvest note: punch downs three times daily, one full circuit; Babo fell from 12.4 on 11 September to 3.0 at 09:05 on 13 September.')
WHERE w.estate_id=s.estate_id AND w.code='GRN-2026-01' AND w.notes NOT LIKE '%Wendy 2026 harvest note:%';

INSERT INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,kg_handled,payment_status,payroll_scope,notes)
SELECT '15500000-0000-4000-8000-000000000021',s.estate_id,s.id,'wendy-2026-grecanico-harvest-crew','2026-09-09','06:30-14:00','Harvest crew (6 people)','Harvest',2299.53,'unknown','unknown','Six people; elapsed window 06:30-14:00. Break and payable hours were not stated, so regular_hours is intentionally blank. Cooling truck to Raiti.'
FROM seasons s WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE work_date=VALUES(work_date),shift_label=VALUES(shift_label),person_or_crew=VALUES(person_or_crew),role=VALUES(role),kg_handled=VALUES(kg_handled),notes=VALUES(notes);

INSERT INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,kg_handled,payment_status,payroll_scope,notes)
SELECT '15500000-0000-4000-8000-000000000022',s.estate_id,s.id,'wendy-2026-grenache-harvest-crew','2026-09-10','06:30-09:00','Harvest crew (4 people)','Harvest',399.25,'unknown','unknown','Four people; elapsed window 06:30-09:00. Break and payable hours were not stated, so regular_hours is intentionally blank.'
FROM seasons s WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE work_date=VALUES(work_date),shift_label=VALUES(shift_label),person_or_crew=VALUES(person_or_crew),role=VALUES(role),kg_handled=VALUES(kg_handled),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,notes)
SELECT '15500000-0000-4000-8000-000000000031',s.estate_id,s.id,w.id,NULL,'2026-09-10 00:00:00','Soft press',1.8,'bar','Wendy note: soft press on 10 September at 1.8 bar; exact time not recorded.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),amount=VALUES(amount),unit=VALUES(unit),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT '15500000-0000-4000-8000-000000000032',s.estate_id,s.id,w.id,c.id,'2026-09-11 00:00:00','First rack - Wendy source instruction','Clean/open Tank #5; open Tank #3; pump Tank #3 to Tank #5; discard the last material at the bottom of Tank #3; rinse Tank #3; open Tank #5 and rack back to Tank #3. Date recorded; exact time and completion confirmation not recorded.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
JOIN cellar_containers c ON c.estate_id=s.estate_id AND c.code='T-06'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,scheduled_at,quantity,unit,reason_text,recorded_by)
SELECT '15500000-0000-4000-8000-000000000041',s.estate_id,w.id,'EnartisFerm ES181','yeast','planned','2026-09-11 00:00:00',500,'g','Wendy preparation note: 5 L water at 35 C; mix 500 g ES181 and rest 20 minutes; add a glass of Grecanico from the tank to equalize temperature. Completion not explicitly confirmed.','Wendy Harvest 2026 note'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),event_status=VALUES(event_status),scheduled_at=VALUES(scheduled_at),quantity=VALUES(quantity),unit=VALUES(unit),reason_text=VALUES(reason_text),recorded_by=VALUES(recorded_by);

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,scheduled_at,quantity,unit,reason_text,recorded_by)
SELECT '15500000-0000-4000-8000-000000000042',s.estate_id,w.id,'Unspecified yeast - Wendy note','yeast','planned','2026-09-10 00:00:00',180,NULL,'Wendy note records quantity 180 but does not state a unit or product. Preparation: 5 L water plus one spoon sugar; cool mixture to the 25 C must temperature; add into a hole on each side and cover the must. Completion not explicitly confirmed.','Wendy Harvest 2026 note'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),event_status=VALUES(event_status),scheduled_at=VALUES(scheduled_at),quantity=VALUES(quantity),unit=VALUES(unit),reason_text=VALUES(reason_text),recorded_by=VALUES(recorded_by);

INSERT INTO enology_test_requests
  (id,estate_id,season_id,wine_lot_id,requested_at,due_at,process_stage,sample_type,sample_scope,analytes_json,status,requested_by,notes)
SELECT '15500000-0000-4000-8000-000000000051',s.estate_id,s.id,w.id,'2026-09-11 00:00:00','2026-09-11 00:00:00','fermentation','must','Tank #3: green bottle for catechins; panna bottle for catechins and NTU',JSON_ARRAY('catechins','turbidity'),'scheduled','Wendy Harvest 2026 note','Date recorded; sampling time and result values not provided. Keep bottles/results linked to this exact lot.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE due_at=VALUES(due_at),sample_scope=VALUES(sample_scope),analytes_json=VALUES(analytes_json),status=VALUES(status),requested_by=VALUES(requested_by),notes=VALUES(notes);

INSERT INTO enology_test_requests
  (id,estate_id,season_id,wine_lot_id,requested_at,due_at,process_stage,sample_type,sample_scope,analytes_json,status,requested_by,notes)
SELECT '15500000-0000-4000-8000-000000000052',s.estate_id,s.id,w.id,'2026-09-11 00:00:00','2026-09-11 00:00:00','fermentation','must','Tank #44: green bottle for catechins; panna bottle for catechins and NTU',JSON_ARRAY('catechins','turbidity'),'scheduled','Wendy Harvest 2026 note','Date recorded; sampling time and result values not provided. Keep bottles/results linked to this exact lot.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE due_at=VALUES(due_at),sample_scope=VALUES(sample_scope),analytes_json=VALUES(analytes_json),status=VALUES(status),requested_by=VALUES(requested_by),notes=VALUES(notes);

-- Correct the already-present 12:35 Tank #44 row instead of creating a duplicate.
UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-T'
SET f.babo=11.8,f.temp_c=25,f.status='wendy_source_note',
    f.sensory_observation='Wendy note: Tank #44 at 12:35 on 13 September, Babo 11.8 and 25 C.'
WHERE f.estate_id='00000000-0000-4000-8000-000000000001' AND f.observed_at='2026-09-13 12:35:00';

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,cap_management,addition_action,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,x.vessel_name,'fermentation',x.temp_c,x.babo,x.cap_management,x.addition_action,x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '15500000-0000-4000-8000-000000000061' id,'wendy-2026-grc-t44-0912' source_id,'GRC-2026-01-T' lot_code,'2026-09-12 00:00:00' observed_at,'T-44' vessel_name,22 temp_c,16 babo,NULL cap_management,NULL addition_action,'Wendy note: Tank #44 on 12 September, Babo 16 and 22 C; exact time not recorded.' note,'wendy_source_note_date_only' status
  UNION ALL SELECT '15500000-0000-4000-8000-000000000062','wendy-2026-grc-t03-0912','GRC-2026-01-P','2026-09-12 00:00:00','T-06',NULL,17.4,NULL,NULL,'Wendy note: Tank #3 on 12 September, Babo 17.4; temperature and exact time not recorded.','wendy_source_note_date_only'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000063','wendy-2026-grc-t03-0913-first','GRC-2026-01-P','2026-09-13 00:00:00','T-06',15,19,NULL,NULL,'Wendy note: first Tank #3 reading listed on 13 September, Babo 19 and 15 C; exact time not recorded.','wendy_source_note_date_only'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000064','wendy-2026-grc-t44-0913-first','GRC-2026-01-T','2026-09-13 00:00:00','T-44',25,15,NULL,NULL,'Wendy note: first Tank #44 reading listed on 13 September, Babo 15 and 25 C; exact time not recorded.','wendy_source_note_date_only'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000065','wendy-2026-grc-t03-0913-1235','GRC-2026-01-P','2026-09-13 12:35:00','T-06',15,16.9,NULL,NULL,'Wendy note: Tank #3 at 12:35 on 13 September, Babo 16.9 and 15 C.','wendy_source_note'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000066','wendy-2026-grenache-0911-punchdowns','GRN-2026-01','2026-09-11 00:00:00','M-01',NULL,NULL,'Three punch downs: morning, noon and evening; one full circuit each.',NULL,'Wendy note: aggregate daily punch-down instruction/completion record; exact individual times not recorded.','wendy_source_note_date_only'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000067','wendy-2026-grenache-0911-noon','GRN-2026-01','2026-09-11 12:00:00','M-01',26,12.4,'Punch down - one full circuit',NULL,'Wendy note says noon sample; exact minute not recorded.','wendy_source_note_approx_time'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000068','wendy-2026-grenache-0911-evening','GRN-2026-01','2026-09-11 18:00:00','M-01',25,12,'Punch down - one full circuit',NULL,'Wendy note says evening sample; exact time not recorded.','wendy_source_note_approx_time'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000069','wendy-2026-grenache-0912-0939','GRN-2026-01','2026-09-12 09:39:00','M-01',27,8,'Punch down - one full circuit',NULL,'Wendy morning punch-down reading.','wendy_source_note'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000070','wendy-2026-grenache-0912-1214','GRN-2026-01','2026-09-12 12:14:00','M-01',NULL,NULL,'Punch down - one full circuit',NULL,'Wendy midday punch down; no Babo or temperature recorded.','wendy_source_note'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000071','wendy-2026-grenache-0912-1834','GRN-2026-01','2026-09-12 18:34:00','M-01',27,4.3,'Punch down - one full circuit',NULL,'Wendy evening punch-down reading.','wendy_source_note'
  UNION ALL SELECT '15500000-0000-4000-8000-000000000072','wendy-2026-grenache-0913-0905','GRN-2026-01','2026-09-13 09:05:00','M-01',27,3,'Punch down - one full circuit',NULL,'Wendy morning punch-down reading.','wendy_source_note'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code=x.lot_code
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),temp_c=VALUES(temp_c),babo=VALUES(babo),cap_management=VALUES(cap_management),addition_action=VALUES(addition_action),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

-- If the old 12:35 Tank #44 row did not exist, add it now with a stable source key.
INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,sensory_observation,owner_text,status)
SELECT '15500000-0000-4000-8000-000000000073',s.estate_id,w.id,'wendy-2026-grc-t44-0913-1235','2026-09-13 12:35:00','T-44','fermentation',25,11.8,'Wendy note: Tank #44 at 12:35 on 13 September, Babo 11.8 and 25 C.','Wendy','wendy_source_note'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
AND NOT EXISTS (SELECT 1 FROM fermentation_observations f WHERE f.estate_id=s.estate_id AND f.wine_lot_id=w.id AND f.observed_at='2026-09-13 12:35:00')
ON DUPLICATE KEY UPDATE temp_c=VALUES(temp_c),babo=VALUES(babo),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

-- Today's owner-confirmed readings update the already-present 18:00 volume-note
-- observations so the tank cards and WhatsApp history have one current row.
UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-T'
SET f.babo=2.2,f.temp_c=26,f.status='owner_confirmed',
    f.sensory_observation=CONCAT_WS(' ',NULLIF(f.sensory_observation,''),'Owner update 15 September: small white Tank #44, Babo 2.2 and 26 C.')
WHERE f.estate_id='00000000-0000-4000-8000-000000000001' AND f.observed_at='2026-09-15 18:00:00';

UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-P'
SET f.babo=12.2,f.temp_c=18,f.status='owner_confirmed',
    f.sensory_observation=CONCAT_WS(' ',NULLIF(f.sensory_observation,''),'Owner update 15 September: big white Tank #3 (system T-06), Babo 12.2 and 18 C.')
WHERE f.estate_id='00000000-0000-4000-8000-000000000001' AND f.observed_at='2026-09-15 18:00:00';

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,sensory_observation,owner_text,status)
SELECT '15500000-0000-4000-8000-000000000074',s.estate_id,w.id,'owner-2026-grc-t44-0915','2026-09-15 18:00:00','T-44','fermentation',26,2.2,'Owner update 15 September: small white Tank #44, Babo 2.2 and 26 C.','Owner','owner_confirmed'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
AND NOT EXISTS (SELECT 1 FROM fermentation_observations f WHERE f.estate_id=s.estate_id AND f.wine_lot_id=w.id AND f.observed_at='2026-09-15 18:00:00')
ON DUPLICATE KEY UPDATE temp_c=VALUES(temp_c),babo=VALUES(babo),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,sensory_observation,owner_text,status)
SELECT '15500000-0000-4000-8000-000000000075',s.estate_id,w.id,'owner-2026-grc-t03-0915','2026-09-15 18:00:00','T-06','fermentation',18,12.2,'Owner update 15 September: big white Tank #3 (system T-06), Babo 12.2 and 18 C.','Owner','owner_confirmed'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.estate_id='00000000-0000-4000-8000-000000000001' AND s.vintage_year=2026
AND NOT EXISTS (SELECT 1 FROM fermentation_observations f WHERE f.estate_id=s.estate_id AND f.wine_lot_id=w.id AND f.observed_at='2026-09-15 18:00:00')
ON DUPLICATE KEY UPDATE temp_c=VALUES(temp_c),babo=VALUES(babo),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);
