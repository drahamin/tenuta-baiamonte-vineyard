-- User-confirmed 2023 Baiamonte harvest chronology supplied 2026-08-19.
-- Picking and crushing are deliberately stored as separate facts.

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_id,source_note_name)
VALUES
  ('00000000-0000-4000-8000-000000000001',2023,'Grecanico','2023-09-23','2023-09-24','day','user_confirmed','Picked September 23 and 24, 2023. First lot received 24 hours skin contact and second lot 12 hours; crushed September 25.','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology'),
  ('00000000-0000-4000-8000-000000000001',2023,'Grenache','2023-09-24','2023-09-24','day','user_confirmed','Picked September 24, 2023; crushed October 13.','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology'),
  ('00000000-0000-4000-8000-000000000001',2023,'Nerello Mascalese','2023-10-08','2023-10-08','day','user_confirmed','Picked October 8, 2023; crushed October 26.','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology')
ON DUPLICATE KEY UPDATE
  first_pick_date=VALUES(first_pick_date),
  last_pick_date=VALUES(last_pick_date),
  harvest_date_precision=VALUES(harvest_date_precision),
  evidence_status=VALUES(evidence_status),
  reconciliation_note=VALUES(reconciliation_note),
  source_note_id=VALUES(source_note_id),
  source_note_name=VALUES(source_note_name);

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,details,evidence_status,canonical_table,canonical_key)
VALUES
  ('51000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-grecanico-first-pick','2023-09-23',2023,'day','harvest','Grecanico','Picked September 23 and September 24. September 23 fruit received 24 hours skin contact; September 24 fruit received 12 hours skin contact.','user_confirmed','vintage_summaries','2023:Grecanico'),
  ('51000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-grecanico-crush','2023-09-25',2023,'day','cellar','Grecanico crushing','Crushed September 25, 2023 after the recorded skin-contact periods.','user_confirmed',NULL,NULL),
  ('51000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-grenache-pick','2023-09-24',2023,'day','harvest','Grenache','Picked September 24, 2023.','user_confirmed','vintage_summaries','2023:Grenache'),
  ('51000000-0000-4000-8000-000000000004','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-grenache-crush','2023-10-13',2023,'day','cellar','Grenache crushing','Crushed October 13, 2023.','user_confirmed',NULL,NULL),
  ('51000000-0000-4000-8000-000000000005','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-nerello-pick','2023-10-08',2023,'day','harvest','Nerello Mascalese','Picked October 8, 2023.','user_confirmed','vintage_summaries','2023:Nerello Mascalese'),
  ('51000000-0000-4000-8000-000000000006','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-harvest-2023','User-confirmed 2023 harvest chronology','2023-nerello-crush','2023-10-26',2023,'day','cellar','Nerello Mascalese crushing','Crushed October 26, 2023.','user_confirmed',NULL,NULL)
ON DUPLICATE KEY UPDATE
  fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),
  details=VALUES(details),evidence_status=VALUES(evidence_status),canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key);
