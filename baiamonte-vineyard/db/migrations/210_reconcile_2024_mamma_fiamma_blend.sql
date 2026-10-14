-- Owner correction: the 2024 red wine was Mamma Fiamma, made by blending
-- Grenache with Nerello Mascalese. The existing 1,558 kg / 881 L summary had
-- been labeled only as Nerello. The component weights are not known, so the
-- combined lot must remain visible but cannot train either varietal yield.

UPDATE vintage_summaries
SET variety_name='Mamma Fiamma · Nerello Mascalese / Grenache blend',
    evidence_status='owner_confirmed_blend',
    reconciliation_note='Owner confirmed 2026-10-14 that the 2024 red wine was Mamma Fiamma, a Nerello Mascalese and Grenache blend. The recorded 1,558 kg red-fruit total and 881 L final red wine belong to the combined blend; component kilograms and liters are unknown and must not be attributed to either variety for yield learning.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2024
  AND LOWER(TRIM(variety_name)) LIKE 'nerello%'
  AND COALESCE(grapes_kg,0)>0;

UPDATE vintage_summaries
SET reconciliation_note=CONCAT_WS(' ',NULLIF(reconciliation_note,''),'Owner confirmed 2026-10-14 that the 2024 Grenache was blended with Nerello Mascalese as Mamma Fiamma. The component quantity remains unknown; see the combined Mamma Fiamma summary.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND vintage_year=2024
  AND LOWER(TRIM(variety_name))='grenache'
  AND COALESCE(grapes_kg,0)=0;

UPDATE historical_note_facts
SET subject='Mamma Fiamma · 2024 red blend',
    details='White 1,662 kg. The 1,558 kg red-fruit total and later reconciled 881 L red wine produced Mamma Fiamma, an owner-confirmed blend of Nerello Mascalese and Grenache. Component kilograms and liters are not recorded.',
    conflict_note='The source note assigned the red quantity to Nerello and listed Grenache as 0 kg. The owner subsequently confirmed the Grenache was mixed with Nerello in Mamma Fiamma; no component split is inferred.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_note_id='p18091'
  AND fact_key='2024-yield';

UPDATE historical_note_facts
SET details='Bottled production: White 1,182 plus 6 magnums; Mamma Fiamma red blend 1,128 plus 6 magnums.',
    conflict_note='Owner confirmed 2026-10-14 that the 2024 red wine was Mamma Fiamma, a Grenache and Nerello Mascalese blend.'
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_note_id='p20877'
  AND fact_key='2024-bottled';

INSERT INTO audit_events
  (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-210','reconcile_2024_mamma_fiamma_blend','vintage_summary','2024:Mamma Fiamma',
       JSON_OBJECT(
         'wine_name','Mamma Fiamma',
         'vintage_year',2024,
         'composition','Nerello Mascalese and Grenache blend',
         'combined_grapes_kg',1558,
         'finished_wine_l',881,
         'component_split','unknown',
         'prediction_policy','exclude from single-variety yield learning',
         'evidence','owner confirmation 2026-10-14'
       )
FROM estates e
WHERE e.id='00000000-0000-4000-8000-000000000001'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events a
    WHERE a.estate_id=e.id
      AND a.actor='migration-210'
      AND a.action='reconcile_2024_mamma_fiamma_blend'
      AND a.entity_id='2024:Mamma Fiamma'
  );
