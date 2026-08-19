-- Additional user-confirmed harvest evidence supplied 2026-08-19.
-- The 2023 Grenache date is retained as an earlier lot, not treated as a
-- replacement for the previously confirmed September 24 pick.

UPDATE vintage_summaries
SET first_pick_date='2023-09-17',
    last_pick_date='2023-09-24',
    harvest_date_precision='day',
    evidence_status='user_confirmed',
    reconciliation_note='Picked September 17 and September 24, 2023. September 17: 08:00-10:00, 3 people, 20 crates and one 400 L mastalone. Pressed October 4 at 50-70 bar into approximately three quarters of tank 13; approximately 300 x 750 ml bottles. A separate press note states approximately 120 bar and Demi 8 bottles; wording retained without interpreting the container or volume.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2023
  AND LOWER(TRIM(variety_name))='grenache';

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_id,source_note_name)
VALUES
  ('00000000-0000-4000-8000-000000000001',2025,'Grecanico','2025-09-11','2025-09-11','day','user_confirmed','User confirmed Grecanico was picked September 11, 2025.','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2025,'Grenache','2025-09-17','2025-09-17','day','user_confirmed','User confirmed Grenache was picked September 17, 2025.','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2025,'Nerello Mascalese','2025-09-23','2025-09-23','day','user_confirmed','User reconfirmed Nerello was picked September 23, 2025.','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates')
ON DUPLICATE KEY UPDATE
  first_pick_date=VALUES(first_pick_date),
  last_pick_date=VALUES(last_pick_date),
  harvest_date_precision=VALUES(harvest_date_precision),
  evidence_status=VALUES(evidence_status),
  reconciliation_note=VALUES(reconciliation_note),
  source_note_id=VALUES(source_note_id),
  source_note_name=VALUES(source_note_name);

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,quantity_value,quantity_unit,details,evidence_status,canonical_table,canonical_key,conflict_note)
VALUES
  ('52000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-grenache-2023','User-confirmed 2023 Grenache detail','2023-grenache-early-pick','2023-09-17',2023,'day','harvest','Grenache',20,'crates','Harvested 08:00-10:00 by 3 people; 20 crates into one 400 L mastalone. September 24 remains the later confirmed Grenache pick.','user_confirmed','vintage_summaries','2023:Grenache',NULL),
  ('52000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-grenache-2023','User-confirmed 2023 Grenache detail','2023-grenache-harvest-labor','2023-09-17',2023,'day','labor','Grenache harvest crew',6,'h','Three people worked from 08:00 to 10:00; 6 person-hours calculated from the supplied crew and duration.','derived_confirmed',NULL,NULL,NULL),
  ('52000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-grenache-2023','User-confirmed 2023 Grenache detail','2023-grenache-press','2023-10-04',2023,'day','cellar','Grenache pressing',NULL,NULL,'Pressed at 50-70 bar into approximately three quarters of tank 13. A separate line states approximately 120 bar and Demi 8 bottles; preserved verbatim in the evidence trail without inventing a container or volume conversion.','user_confirmed',NULL,NULL,'The relationship between the 50-70 bar press and the separate approximately 120 bar line is not specified.'),
  ('52000000-0000-4000-8000-000000000004','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-grenache-2023','User-confirmed 2023 Grenache detail','2023-grenache-bottles','2023-10-04',2023,'day','cellar','Grenache approximate bottle output',300,'750ml bottles','Approximately 300 x 750 ml bottles; retained as approximate historical evidence and not promoted to an exact inventory balance.','user_confirmed',NULL,NULL,NULL),
  ('52000000-0000-4000-8000-000000000005','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates','2025-grecanico-pick','2025-09-11',2025,'day','harvest','Grecanico',NULL,NULL,'Picked September 11, 2025.','user_confirmed','vintage_summaries','2025:Grecanico',NULL),
  ('52000000-0000-4000-8000-000000000006','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates','2025-grenache-pick','2025-09-17',2025,'day','harvest','Grenache',NULL,NULL,'Picked September 17, 2025.','user_confirmed','vintage_summaries','2025:Grenache',NULL),
  ('52000000-0000-4000-8000-000000000007','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2025','User-confirmed 2025 harvest dates','2025-nerello-pick','2025-09-23',2025,'day','harvest','Nerello Mascalese',NULL,NULL,'Picked September 23, 2025; reconfirms the existing exact Nerello date.','user_confirmed','vintage_summaries','2025:Nerello Mascalese',NULL)
ON DUPLICATE KEY UPDATE
  fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),
  quantity_value=VALUES(quantity_value),quantity_unit=VALUES(quantity_unit),details=VALUES(details),evidence_status=VALUES(evidence_status),
  canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key),conflict_note=VALUES(conflict_note);
