-- The earlier owner-entered 2024 vintage total (2,357 L) predates the later
-- source-backed final figures: 886 L Grecanico plus 881 L Mamma Fiamma.
-- Reconcile the total to those final rows so the chart does not invent a
-- 590 L unallocated stream. Mamma Fiamma remains a combined Nerello/Grenache
-- wine because the component split is unknown.

UPDATE vintage_summaries
SET wine_l=1767.000,
    bottle_equivalents_750ml=2356,
    evidence_status='owner_authoritative_reconciled',
    reconciliation_note='Reconciled 2026-10-16 to the later source-backed final volumes: 886 L Grecanico plus 881 L Mamma Fiamma (Nerello Mascalese/Grenache blend) = 1,767 L. The earlier 2,357 L total caused a false 590 L unallocated chart segment and is superseded.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2024
  AND LOWER(TRIM(variety_name))='vintage total';

UPDATE historical_bottling_summaries
SET wine_l=1767.000,
    bottle_equivalents_750ml=2356,
    completion_status='equivalent_only',
    evidence_note='Reconciled 2026-10-16 from later source-backed final wine volumes: 886 L Grecanico plus 881 L Mamma Fiamma = 1,767 L. The 2,356 count is a 750 ml mathematical equivalent, not a physical inventory count.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2024;

INSERT INTO audit_events
  (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-214','reconcile_2024_final_wine_total','vintage_summary','2024:Vintage total',
       JSON_OBJECT('wine_l',1767,'bottle_equivalents_750ml',2356,'grecanico_l',886,'mamma_fiamma_l',881,'unallocated_l',0,'basis','later source-backed final volumes')
FROM estates e
WHERE e.id='00000000-0000-4000-8000-000000000001'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events a
    WHERE a.estate_id=e.id AND a.actor='migration-214'
      AND a.action='reconcile_2024_final_wine_total'
      AND a.entity_id='2024:Vintage total'
  );
