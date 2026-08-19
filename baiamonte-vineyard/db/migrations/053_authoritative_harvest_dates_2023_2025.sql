-- Authoritative harvest-date matrix confirmed by the user on 2026-08-19.
-- These nine exact variety/year dates supersede conflicting harvest-date
-- claims while preserving those source records in the audit trail.

INSERT INTO vintage_summaries
  (estate_id,vintage_year,variety_name,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_id,source_note_name)
VALUES
  ('00000000-0000-4000-8000-000000000001',2023,'Grecanico','2023-09-23','2023-09-23','day','user_authoritative','Authoritative harvest-date list: Grecanico picked September 23, 2023.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2023,'Grenache','2023-09-24','2023-09-24','day','user_authoritative','Authoritative harvest-date list: Grenache picked September 24, 2023. This supersedes the separate September 17 harvest-date claim.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2023,'Nerello Mascalese','2023-10-08','2023-10-08','day','user_authoritative','Authoritative harvest-date list: Nerello picked October 8, 2023.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2024,'Grecanico','2024-09-11','2024-09-11','day','user_authoritative','Authoritative harvest-date list: Grecanico picked September 11, 2024.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2024,'Grenache','2024-09-23','2024-09-23','day','user_authoritative','Authoritative harvest-date list: Grenache picked September 23, 2024, on the shared Nerello/Grenache harvest date.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2024,'Nerello Mascalese','2024-09-23','2024-09-23','day','user_authoritative','Authoritative harvest-date list: Nerello picked September 23, 2024, on the shared Nerello/Grenache harvest date.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2025,'Grecanico','2025-09-11','2025-09-11','day','user_authoritative','Authoritative harvest-date list: Grecanico picked September 11, 2025.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2025,'Grenache','2025-09-17','2025-09-17','day','user_authoritative','Authoritative harvest-date list: Grenache picked September 17, 2025.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates'),
  ('00000000-0000-4000-8000-000000000001',2025,'Nerello Mascalese','2025-09-23','2025-09-23','day','user_authoritative','Authoritative harvest-date list: Nerello picked September 23, 2025.','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates')
ON DUPLICATE KEY UPDATE
  first_pick_date=VALUES(first_pick_date),
  last_pick_date=VALUES(last_pick_date),
  harvest_date_precision=VALUES(harvest_date_precision),
  evidence_status=VALUES(evidence_status),
  reconciliation_note=VALUES(reconciliation_note),
  source_note_id=VALUES(source_note_id),
  source_note_name=VALUES(source_note_name);

UPDATE historical_note_facts
SET fact_date=NULL,
    date_precision='unknown',
    evidence_status='superseded_date',
    canonical_table=NULL,
    canonical_key=NULL,
    conflict_note='Earlier date discarded and replaced by the user-authoritative 2023-2025 harvest-date matrix.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND fact_year BETWEEN 2023 AND 2025
  AND fact_date IS NOT NULL
  AND source_note_id<>'codex-thread-2026-08-19-authoritative-harvest-dates'
  AND (domain='harvest' OR id='52000000-0000-4000-8000-000000000002');

UPDATE historical_note_facts
SET conflict_note=CONCAT_WS(' ',NULLIF(conflict_note,''),'Any earlier associated pick date was discarded; this pressing detail remains separately retained without supplying a harvest date.')
WHERE id='52000000-0000-4000-8000-000000000003';

INSERT INTO historical_note_facts
  (id,estate_id,source_note_id,source_note_name,fact_key,fact_date,fact_year,date_precision,domain,subject,details,evidence_status,canonical_table,canonical_key)
VALUES
  ('53000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2023-grecanico-authoritative-pick','2023-09-23',2023,'day','harvest','Grecanico','Authoritative pick date: September 23, 2023.','user_authoritative','vintage_summaries','2023:Grecanico'),
  ('53000000-0000-4000-8000-000000000002','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2023-grenache-authoritative-pick','2023-09-24',2023,'day','harvest','Grenache','Authoritative pick date: September 24, 2023.','user_authoritative','vintage_summaries','2023:Grenache'),
  ('53000000-0000-4000-8000-000000000003','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2023-nerello-authoritative-pick','2023-10-08',2023,'day','harvest','Nerello Mascalese','Authoritative pick date: October 8, 2023.','user_authoritative','vintage_summaries','2023:Nerello Mascalese'),
  ('53000000-0000-4000-8000-000000000004','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2024-grecanico-authoritative-pick','2024-09-11',2024,'day','harvest','Grecanico','Authoritative pick date: September 11, 2024.','user_authoritative','vintage_summaries','2024:Grecanico'),
  ('53000000-0000-4000-8000-000000000005','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2024-grenache-authoritative-pick','2024-09-23',2024,'day','harvest','Grenache','Authoritative shared Nerello/Grenache pick date: September 23, 2024.','user_authoritative','vintage_summaries','2024:Grenache'),
  ('53000000-0000-4000-8000-000000000006','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2024-nerello-authoritative-pick','2024-09-23',2024,'day','harvest','Nerello Mascalese','Authoritative shared Nerello/Grenache pick date: September 23, 2024.','user_authoritative','vintage_summaries','2024:Nerello Mascalese'),
  ('53000000-0000-4000-8000-000000000007','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2025-grecanico-authoritative-pick','2025-09-11',2025,'day','harvest','Grecanico','Authoritative pick date: September 11, 2025.','user_authoritative','vintage_summaries','2025:Grecanico'),
  ('53000000-0000-4000-8000-000000000008','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2025-grenache-authoritative-pick','2025-09-17',2025,'day','harvest','Grenache','Authoritative pick date: September 17, 2025.','user_authoritative','vintage_summaries','2025:Grenache'),
  ('53000000-0000-4000-8000-000000000009','00000000-0000-4000-8000-000000000001','codex-thread-2026-08-19-authoritative-harvest-dates','Authoritative 2023-2025 harvest dates','2025-nerello-authoritative-pick','2025-09-23',2025,'day','harvest','Nerello Mascalese','Authoritative pick date: September 23, 2025.','user_authoritative','vintage_summaries','2025:Nerello Mascalese')
ON DUPLICATE KEY UPDATE
  fact_date=VALUES(fact_date),fact_year=VALUES(fact_year),date_precision=VALUES(date_precision),domain=VALUES(domain),subject=VALUES(subject),
  details=VALUES(details),evidence_status=VALUES(evidence_status),canonical_table=VALUES(canonical_table),canonical_key=VALUES(canonical_key);
