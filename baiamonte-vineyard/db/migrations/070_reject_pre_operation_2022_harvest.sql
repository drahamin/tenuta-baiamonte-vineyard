-- The owner confirmed on 2026-08-20 that Baiamonte's first harvest was 2023
-- and that no Baiamonte harvest occurred in 2022. Preserve the imported source
-- rows for audit, but remove their quantities from every canonical total.

UPDATE vintage_summaries
SET grapes_kg=NULL,
    wine_l=NULL,
    cassette_count=NULL,
    evidence_status='rejected_misattributed',
    reconciliation_note=CONCAT_WS(' ',NULLIF(reconciliation_note,''),'Owner confirmed no Baiamonte harvest occurred in 2022; this row is retained only as rejected source evidence.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year<2023;

UPDATE historical_note_facts
SET evidence_status='rejected_misattributed',
    conflict_note=CONCAT_WS(' ',NULLIF(conflict_note,''),'Owner confirmed Baiamonte operations began with the 2023 harvest; this pre-operation harvest quantity is not authoritative.'),
    canonical_table=NULL,
    canonical_key=NULL
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND domain='harvest'
  AND fact_year<2023;
