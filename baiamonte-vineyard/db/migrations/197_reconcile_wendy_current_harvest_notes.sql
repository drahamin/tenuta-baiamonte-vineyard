-- Wendy's current Harvest 2026 notes, supplied 30 September 2026.
-- Later source corrections supersede the earlier Wendy transcription. Values
-- left blank in the source remain NULL. "Morning" and "evening" use clearly
-- labelled approximate storage times. Owner-confirmed unit corrections remain
-- authoritative: CLARIL AF is 60 g and NUTRIFERM AROM PLUS is 30 g/hL.

INSERT INTO notes (id,estate_id,note_date,title,body,tags,related_type,related_id)
SELECT '19700000-0000-4000-8000-000000000001',s.estate_id,'2026-09-30 19:45:00',
       'Wendy - current Harvest 2026 cellar chronology',
       'Current Wendy chronology supplied 30 September 2026. Grecanico: picked 9 September; 199 crates; 2,588.08 kg gross; 1.45 kg crate tare; soft pressed at 1.8 bar on 10 September. Tank #3 and Tank #44 fermentation readings are reconciled through 26 September. Tank #44 was racked 22 September and transferred on 28 September into three demijohns identified in the note as L54; the note records "230 sulfur" added to each but does not state a unit or exact sulfur product. Tank #3 was racked 23 September. Grenache: picked 10 September; 35 crates; 450 kg gross; pressed 16 September at approximately 16:50 into 280 L in a stainless tank; Babo and temperature were blank. Nerello Mascalese: picked 25 September; 172 crates; 2,389 kg gross; approximately 1,600 L must. The note records inoculation, nutrient at the package rate, and pump-overs/readings through 30 September. Existing owner-confirmed corrections remain authoritative: CLARIL AF 60 g (not mg) in the small Grecanico lot and NUTRIFERM AROM PLUS 30 g/hL (not g/kg) in Nerello.',
       JSON_ARRAY('wendy','harvest','2026','cellar','current-chronology','source-note'),
       'season',s.id
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE note_date=VALUES(note_date),title=VALUES(title),body=VALUES(body),tags=VALUES(tags),related_type=VALUES(related_type),related_id=VALUES(related_id);

-- Correct the two Tank #3 readings whose earlier transcription was superseded.
UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-P'
SET f.babo=16.8,f.temp_c=15,f.vessel_name='T-03',f.status='wendy_current_note_date_only',
    f.sensory_observation='Wendy current note: first Tank #3 reading on 13 September was Babo 16.8 and 15 C; exact time not recorded. Supersedes the earlier 19 Babo transcription.'
WHERE f.source_observation_id='wendy-2026-grc-t03-0913-first';

UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-P'
SET f.babo=16.0,f.temp_c=15,f.vessel_name='T-03',f.status='wendy_current_note',
    f.sensory_observation='Wendy current note: Tank #3 at 12:35 on 13 September was Babo 16.0 and 15 C. Supersedes the earlier 16.9 Babo transcription.'
WHERE f.source_observation_id='wendy-2026-grc-t03-0913-1235';

UPDATE fermentation_observations f
JOIN wine_lots w ON w.id=f.wine_lot_id AND w.code='GRC-2026-01-P'
SET f.babo=12.2,f.temp_c=22,f.vessel_name='T-03',f.status='wendy_current_note_date_only',
    f.sensory_observation='Wendy current note: Tank #3 on 15 September was Babo 12.2 and 22 C; exact time not recorded.'
WHERE f.source_observation_id='owner-2026-grc-t03-0915';

-- Add all newly supplied Grecanico readings. Midnight is date-only, not an
-- asserted observation time. Qualitative "almost 0" is not converted to zero.
INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,cap_management,addition_action,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,x.vessel_name,'fermentation',x.temp_c,x.babo,x.cap_management,x.addition_action,x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '19700000-0000-4000-8000-000000000011' id,'wendy-current-grc-p-0914' source_id,'GRC-2026-01-P' lot_code,'2026-09-14 00:00:00' observed_at,'T-03' vessel_name,17 temp_c,14 babo,NULL cap_management,NULL addition_action,'Wendy current note: Tank #3 on 14 September, Babo 14 and 17 C; exact time not recorded.' note,'wendy_current_note_date_only' status
  UNION ALL SELECT '19700000-0000-4000-8000-000000000012','wendy-current-grc-t-0914','GRC-2026-01-T','2026-09-14 00:00:00','T-44',24,7.9,NULL,'CLARIL AF 60 g','Wendy current note: Tank #44 on 14 September, Babo 7.9 and 24 C. The note says 60 mg, but the owner explicitly corrected the applied CLARIL AF quantity to 60 g.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000013','wendy-current-grc-p-0916','GRC-2026-01-P','2026-09-16 00:00:00','T-03',18,7.6,NULL,NULL,'Wendy current note: Tank #3 on 16 September, Babo 7.6 and 18 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000014','wendy-current-grc-t-0916','GRC-2026-01-T','2026-09-16 00:00:00','T-44',24,0,NULL,NULL,'Wendy current note: Tank #44 on 16 September, Babo 0 and 24 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000015','wendy-current-grc-p-0917','GRC-2026-01-P','2026-09-17 00:00:00','T-03',17,6.2,NULL,NULL,'Wendy current note: Tank #3 on 17 September, Babo 6.2 and 17 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000016','wendy-current-grc-t-0917','GRC-2026-01-T','2026-09-17 00:00:00','T-44',21,0,NULL,NULL,'Wendy current note: Tank #44 on 17 September, Babo 0 and 21 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000017','wendy-current-grc-p-0919','GRC-2026-01-P','2026-09-19 00:00:00','T-03',17,4,NULL,NULL,'Wendy current note: Tank #3 on 19 September, Babo 4 and 17 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000018','wendy-current-grc-t-0919','GRC-2026-01-T','2026-09-19 00:00:00','T-44',19,0,NULL,NULL,'Wendy current note: Tank #44 on 19 September, Babo 0 and 19 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000019','wendy-current-grc-p-0920','GRC-2026-01-P','2026-09-20 00:00:00','T-03',18,2.1,NULL,NULL,'Wendy current note: Tank #3 on 20 September, Babo 2.1 and 18 C; exact time not recorded.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000020','wendy-current-grc-t-0920-complete','GRC-2026-01-T','2026-09-20 00:00:00','T-44',NULL,NULL,NULL,NULL,'Wendy current note marks Tank #44 fermentation complete on 20 September; no reading values supplied.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000021','wendy-current-grc-p-0925','GRC-2026-01-P','2026-09-25 00:00:00','T-03',19,NULL,NULL,NULL,'Wendy current note: Tank #3 Babo was "almost 0" and temperature 19 C on 25 September. Qualitative Babo is retained in text, not converted to a numeric zero.','wendy_current_note_date_only'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000022','wendy-current-grc-p-0926','GRC-2026-01-P','2026-09-26 00:00:00','T-03',18,0,NULL,NULL,'Wendy current note: Tank #3 on 26 September, Babo 0 and 18 C; exact time not recorded.','wendy_current_note_date_only'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code=x.lot_code
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),temp_c=VALUES(temp_c),babo=VALUES(babo),cap_management=VALUES(cap_management),addition_action=VALUES(addition_action),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

-- Confirm completed white-wine rackings and correct the demijohn transfer date.
INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT '19700000-0000-4000-8000-000000000031',s.estate_id,s.id,w.id,NULL,'2026-09-22 00:00:00','Racking',
       'Wendy current note: Tank #44 racked on 22 September 2026; exact time, source/destination vessels and transferred volume were not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT '19700000-0000-4000-8000-000000000032',s.estate_id,s.id,w.id,NULL,'2026-09-23 00:00:00','Racking',
       'Wendy current note: Tank #3 racked on 23 September 2026. The note says David has a picture of Babo and temperature, but the numeric values and exact time were not supplied.'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-P'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='GRC-2026-01-T'
SET o.operation_at='2026-09-28 00:00:00',
    o.notes='Wendy current note corrects the transfer date to 28 September 2026: Tank #44 wine transferred into three demijohns identified in the note as L54, moved to the vineyard and capped. Exact time, individual fills and whether L54 is capacity or vessel model were not supplied.'
WHERE o.id='19400000-0000-4000-8000-000000000002';

UPDATE cellar_control_profiles cp
JOIN cellar_containers c ON c.id=cp.container_id AND c.code='DJ-GRC-T-SET'
SET cp.manual_reading_at='2026-09-28 00:00:00',cp.manual_updated_at='2026-09-28 00:00:00',
    cp.updated_by='Wendy current chronology 2026-09-30';

INSERT INTO enology_addition_events
  (id,estate_id,wine_lot_id,additive_name,additive_type,event_status,applied_at,quantity,unit,reason_text,approved_by,approved_at,recorded_by)
SELECT '19700000-0000-4000-8000-000000000033',s.estate_id,w.id,'Sulfur addition — exact product pending','other','applied','2026-09-28 00:00:00',230,'source units/demijohn',
       'Wendy current note records "230 sulfur" added to each of three demijohns during the 28 September transfer. The source does not state whether 230 is mg, g, mL or another measure, nor the exact sulfur product/concentration; retain the source quantity but do not calculate a dose or total mass from it.',
       'Cellar team','2026-09-28 00:00:00','Wendy current Harvest 2026 note'
FROM seasons s JOIN wine_lots w ON w.season_id=s.id AND w.code='GRC-2026-01-T'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE additive_name=VALUES(additive_name),additive_type=VALUES(additive_type),event_status=VALUES(event_status),applied_at=VALUES(applied_at),quantity=VALUES(quantity),unit=VALUES(unit),reason_text=VALUES(reason_text),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),recorded_by=VALUES(recorded_by);

-- Grenache press completion. Babo and temperature were blank in the source.
UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id AND w.code='GRN-2026-01'
SET o.operation_at='2026-09-16 16:50:00',o.operation_type='Crush and press completed',o.amount=280,o.unit='L',
    o.notes='Wendy current note: Grenache crushed/pressed 16 September at approximately 16:50, yielding 280 L in the assigned 300 L stainless tank T-45. Babo and temperature were blank and remain unrecorded.'
WHERE o.id='15600000-0000-4000-8000-000000000003';

UPDATE wine_lots w JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET w.volume_l=280,w.notes=CONCAT_WS('\n',NULLIF(w.notes,''),'Wendy current note confirms Grenache press completed 16 September 2026 at approximately 16:50; 280 L transferred to stainless tank T-45. Press-time Babo and temperature were not supplied.')
WHERE w.code='GRN-2026-01' AND COALESCE(w.notes,'') NOT LIKE '%Wendy current note confirms Grenache press completed%';

-- Preserve the two 13 September Grenache punch-down actions even though the
-- source intentionally supplies no new numeric reading for either action.
INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,cap_management,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,'M-01','fermentation',NULL,NULL,'Punch down - one full circuit',x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '19700000-0000-4000-8000-000000000034' id,'wendy-current-grenache-0913-1230' source_id,'2026-09-13 12:30:00' observed_at,'Wendy current note: afternoon punch down at 12:30. Babo was explicitly not required per SV and no temperature value was supplied.' note,'wendy_current_note' status
  UNION ALL SELECT '19700000-0000-4000-8000-000000000035','wendy-current-grenache-0913-evening','2026-09-13 19:00:00','Wendy current note: evening punch down; Babo and temperature were blank. 19:00 is an approximate storage time because the exact time was not supplied.','wendy_current_note_approx_time'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='GRN-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),temp_c=VALUES(temp_c),babo=VALUES(babo),cap_management=VALUES(cap_management),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

-- Nerello readings and punch-down/pump-over chronology. Wendy calls the
-- physical vessel Tank #5; the system identity is T-09.
INSERT INTO fermentation_observations
  (id,estate_id,wine_lot_id,source_observation_id,observed_at,vessel_name,stage,temp_c,babo,cap_management,sensory_observation,owner_text,status)
SELECT x.id,s.estate_id,w.id,x.source_id,x.observed_at,'T-09','fermentation',x.temp_c,x.babo,x.cap_management,x.note,'Wendy',x.status
FROM seasons s
JOIN (
  SELECT '19700000-0000-4000-8000-000000000041' id,'wendy-current-nm-0926' source_id,'2026-09-26 00:00:00' observed_at,16 temp_c,20.3 babo,NULL cap_management,'Wendy current note: Nerello Tank #5 (system T-09) on 26 September, Babo 20.3 and 16 C; exact time not recorded.' note,'wendy_current_note_date_only' status
  UNION ALL SELECT '19700000-0000-4000-8000-000000000042','wendy-current-nm-0927-0915','2026-09-27 09:15:00',16,19,'Pump-over 08:55-09:05','Wendy current note: after the morning pump-over, Babo 19 and 16 C at 09:15.','wendy_current_note'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000043','wendy-current-nm-0927-1910','2026-09-27 19:10:00',17.5,18.9,'Pump-over 18:50-19:25','Wendy current note: during/after the evening pump-over window, Babo 18.9 and 17.5 C at 19:10.','wendy_current_note'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000044','wendy-current-nm-0928-morning','2026-09-28 09:00:00',20,16.3,'Morning pump-over','Wendy current note: morning pump-over, Babo 16.3 and 20 C. 09:00 is an approximate storage time because the exact time was not supplied.','wendy_current_note_approx_time'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000045','wendy-current-nm-0928-evening','2026-09-28 19:00:00',NULL,NULL,'Evening pump-over','Wendy current note: evening pump-over; Babo and temperature were blank. 19:00 is an approximate storage time.','wendy_current_note_approx_time'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000046','wendy-current-nm-0929-evening','2026-09-29 19:00:00',19,10.9,'Evening pump-over','Wendy current note: evening pump-over, Babo 10.9 and 19 C. 19:00 is an approximate storage time.','wendy_current_note_approx_time'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000047','wendy-current-nm-0930-evening','2026-09-30 19:00:00',19,6.9,'Evening pump-over','Wendy current note: evening pump-over, Babo 6.9 and 19 C. CI.MA alcohol and potential-alcohol testing is referenced separately. 19:00 is an approximate storage time.','wendy_current_note_approx_time'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at),vessel_name=VALUES(vessel_name),stage=VALUES(stage),temp_c=VALUES(temp_c),babo=VALUES(babo),cap_management=VALUES(cap_management),sensory_observation=VALUES(sensory_observation),owner_text=VALUES(owner_text),status=VALUES(status);

INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,notes)
SELECT x.id,s.estate_id,s.id,w.id,w.current_container_id,x.operation_at,'Pump-over',x.notes
FROM seasons s
JOIN (
  SELECT '19700000-0000-4000-8000-000000000051' id,'2026-09-27 08:55:00' operation_at,'Nerello pump-over ran 08:55-09:05; Wendy source.' notes
  UNION ALL SELECT '19700000-0000-4000-8000-000000000052','2026-09-27 18:50:00','Nerello pump-over ran 18:50-19:25; Wendy source.'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000053','2026-09-28 09:00:00','Nerello morning pump-over; exact time not supplied, 09:00 is approximate.'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000054','2026-09-28 19:00:00','Nerello evening pump-over; exact time not supplied, 19:00 is approximate.'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000055','2026-09-29 19:00:00','Nerello evening pump-over; exact time not supplied, 19:00 is approximate.'
  UNION ALL SELECT '19700000-0000-4000-8000-000000000056','2026-09-30 19:00:00','Nerello evening pump-over; exact time not supplied, 19:00 is approximate. CI.MA alcohol and potential-alcohol testing noted.'
) x
JOIN wine_lots w ON w.season_id=s.id AND w.code='NM-2026-01'
WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE container_id=VALUES(container_id),operation_at=VALUES(operation_at),operation_type=VALUES(operation_type),notes=VALUES(notes);

-- Drive the cellar cards and digital tags from the same latest confirmed
-- manual readings as the fermentation pipeline. These values are not sensor
-- readings and retain Wendy as their source.
UPDATE cellar_control_profiles cp
JOIN wine_lots w ON w.current_container_id=cp.container_id AND w.code='GRC-2026-01-P'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET cp.manual_temp_c=18,cp.manual_babo=0,cp.manual_reading_at='2026-09-26 00:00:00',
    cp.manual_updated_at='2026-09-26 00:00:00',cp.updated_by='Wendy current Harvest 2026 note';

UPDATE cellar_control_profiles cp
JOIN wine_lots w ON w.current_container_id=cp.container_id AND w.code='NM-2026-01'
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET cp.manual_temp_c=19,cp.manual_babo=6.9,cp.manual_reading_at='2026-09-30 19:00:00',
    cp.manual_updated_at='2026-09-30 19:00:00',cp.updated_by='Wendy current Harvest 2026 note';

-- Reconcile Nerello labor without inferring breaks or payable hours.
INSERT INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,kg_handled,payment_status,payroll_scope,notes)
SELECT '19700000-0000-4000-8000-000000000061',s.estate_id,s.id,'wendy-current-2026-nerello-harvest-crew','2026-09-25','07:00-10:30','Harvest crew (16 people)','Harvest',2139.60,'unknown','unknown','Wendy current note: 16 people, 07:00-10:30; 172 crates at 10:25. Breaks, individual names and payable hours were not supplied.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE work_date=VALUES(work_date),shift_label=VALUES(shift_label),person_or_crew=VALUES(person_or_crew),role=VALUES(role),kg_handled=VALUES(kg_handled),notes=VALUES(notes);

INSERT INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,kg_handled,payment_status,payroll_scope,notes)
SELECT '19700000-0000-4000-8000-000000000062',s.estate_id,s.id,'wendy-current-2026-nerello-raiti-crew','2026-09-25','11:30-13:30','Cellar crew at Raiti (4 people)','Cellar processing',2139.60,'unknown','unknown','Wendy current note: four people at Raiti, 11:30-13:30. Breaks, individual names and payable hours were not supplied.'
FROM seasons s WHERE s.vintage_year=2026
ON DUPLICATE KEY UPDATE work_date=VALUES(work_date),shift_label=VALUES(shift_label),person_or_crew=VALUES(person_or_crew),role=VALUES(role),kg_handled=VALUES(kg_handled),notes=VALUES(notes);

-- Preserve the 23 September barrels/Tava laboratory request without assigning
-- it to an invented wine lot.
INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,details,evidence_status,canonical_table,canonical_key,conflict_note)
VALUES
  ('19700000-0000-4000-8000-000000000071','00000000-0000-4000-8000-000000000001','wendy-current-harvest-2026','Wendy - current Harvest 2026','barrels-tava-tests','2026-09-23',2026,'day','laboratory','Barrels and Tava','Test each for volatile acidity and Brettanomyces. Exact vessels/lots and results were not supplied.','user_source_note',NULL,NULL,'Do not assign this request to a wine lot until the referenced barrels and Tava are identified.'),
  ('19700000-0000-4000-8000-000000000072','00000000-0000-4000-8000-000000000001','wendy-current-harvest-2026','Wendy - current Harvest 2026','nerello-fermentation-readings','2026-09-30',2026,'day','cellar','Nerello Tank #5 / system T-09','Readings and pump-over chronology from 26-30 September are stored as exact-lot fermentation observations.','user_source_note','fermentation_observations','wendy-current-nm-0926-through-0930',NULL)
ON DUPLICATE KEY UPDATE fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),details=VALUES(details),evidence_status=VALUES(evidence_status),canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key),conflict_note=VALUES(conflict_note);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-197','reconcile_wendy_current_harvest_notes','season','2026',
       JSON_OBJECT('source','Wendy current Harvest 2026 notes supplied 2026-09-30',
                   'corrected_readings',JSON_ARRAY('Grecanico Tank #3 2026-09-13 first: 16.8 Babo','Grecanico Tank #3 2026-09-13 12:35: 16.0 Babo','Grecanico Tank #3 2026-09-15: 22 C'),
                   'added_series',JSON_ARRAY('Grecanico 2026-09-14 through 2026-09-26','Nerello 2026-09-26 through 2026-09-30'),
                   'operations',JSON_ARRAY('Grenache press 2026-09-16 16:50 / 280 L','Grecanico rackings','Nerello pump-overs'),
                   'preserved_corrections',JSON_ARRAY('CLARIL AF 60 g','NUTRIFERM AROM PLUS 30 g/hL'),
                   'unresolved',JSON_ARRAY('Tank #44 sulfur unit/product','23 September photo reading values','23 September barrels/Tava vessel identities'))
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-197' AND a.action='reconcile_wendy_current_harvest_notes');
