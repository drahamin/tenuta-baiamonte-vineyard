-- Apply the authoritative Nerello dates to every retained legacy spelling so
-- dashboard merging and model deduplication cannot select stale metadata.

UPDATE vintage_summaries
SET first_pick_date=CASE vintage_year
      WHEN 2023 THEN '2023-10-08'
      WHEN 2024 THEN '2024-09-23'
      WHEN 2025 THEN '2025-09-23'
    END,
    last_pick_date=CASE vintage_year
      WHEN 2023 THEN '2023-10-08'
      WHEN 2024 THEN '2024-09-23'
      WHEN 2025 THEN '2025-09-23'
    END,
    harvest_date_precision='day',
    evidence_status='user_authoritative',
    reconciliation_note=CONCAT('Authoritative harvest-date matrix: Nerello picked ',CASE vintage_year
      WHEN 2023 THEN 'October 8, 2023.'
      WHEN 2024 THEN 'September 23, 2024.'
      WHEN 2025 THEN 'September 23, 2025.'
    END),
    source_note_id='codex-thread-2026-08-19-authoritative-harvest-dates',
    source_note_name='Authoritative 2023-2025 harvest dates'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year IN (2023,2024,2025)
  AND LOWER(TRIM(variety_name)) LIKE 'nerello%';
