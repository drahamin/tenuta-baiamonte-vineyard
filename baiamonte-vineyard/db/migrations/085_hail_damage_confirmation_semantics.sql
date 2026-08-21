-- Distinguish event coverage from harvest-loss severity. The owner confirms
-- the 2026 hail event was estate-wide: 100% of the estate is in the event
-- scope. The field photographs confirm visible damage, but do not by
-- themselves establish the percentage of crop lost across that scope.

UPDATE vineyard_damage_assessments
SET scope_type='estate',block_id=NULL,variety_id=NULL,affected_area_pct=100.00,
    estimated_yield_loss_pct=NULL,
    notes=CASE
      WHEN source_type='photo_field_report' THEN
        'Photo evidence confirms visible hail damage. Authoritative event scope: whole estate (100% coverage). Estate coverage is not a 100% harvest loss. AI must calculate provisional damage severity and yield-loss percentage with uncertainty from the chronological photo/report chain; Agronomist approval is required before forecast use.'
      ELSE CONCAT_WS('\n',notes,
        'Authoritative event scope: whole estate (100% coverage). AI calculates provisional severity and yield-loss percentage with uncertainty; only an Agronomist-approved estimate may adjust the harvest forecast.')
    END
WHERE event_key='hail-2026-06-27' AND active=1;

-- The owner now confirms that the Agronomist's field interpretation of the
-- initial photographs was a 40% estate harvest-loss estimate. This is a human
-- professional estimate, not an AI derivation. Later qualitative follow-ups
-- remain chronological evidence but do not erase it without a replacement
-- quantified estimate.
UPDATE vineyard_damage_assessments
SET estate_yield_loss_pct=40.00,confidence='medium',review_status='approved',
    approved_by='Sebastiano Vinci',
    notes=CONCAT_WS('\n',notes,
      'Authoritative Agronomist estimate from the initial field inspection and photographs: 40% estate harvest loss. Retain until superseded by a later approved quantitative assessment.')
WHERE id='79000000-0000-4000-8000-000000000001'
  AND event_key='hail-2026-06-27' AND active=1;
