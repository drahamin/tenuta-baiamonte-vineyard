-- Owner correction: the 2026 Grecanico fruit was not destemmed. It went
-- straight to the soft press before CLARIL AF must fining and first racking.

UPDATE enology_addition_events a
JOIN wine_lots w ON w.id=a.wine_lot_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET a.reason_text=CASE
      WHEN w.code='GRC-2026-01-P' THEN 'Owner-confirmed 233.41 g CLARIL AF addition to 1,069.8 L Grecanico must after the fruit went directly to soft pressing without destemming, before the first racking and alcoholic fermentation. Observed rate: 21.82 g/hL; exact application time not supplied.'
      WHEN w.code='GRC-2026-01-T' THEN 'Owner-confirmed 60 g CLARIL AF addition to 275 L Grecanico must after the fruit went directly to soft pressing without destemming, before the first racking and alcoholic fermentation. Observed rate: 21.82 g/hL; exact application time not supplied.'
      ELSE a.reason_text
    END
WHERE w.code IN ('GRC-2026-01-P','GRC-2026-01-T')
  AND LOWER(TRIM(a.additive_name))='claril af'
  AND a.event_status='applied';

UPDATE cellar_operations o
JOIN wine_lots w ON w.id=o.wine_lot_id
JOIN seasons s ON s.id=w.season_id AND s.vintage_year=2026
SET o.notes=REPLACE(
      o.notes,
      'Corrected sequence: destemming, direct soft press, CLARIL AF must fining, first racking, then alcoholic fermentation.',
      'Corrected sequence: fruit went directly to soft press without destemming, followed by CLARIL AF must fining, first racking, then alcoholic fermentation.'
    )
WHERE w.code IN ('GRC-2026-01-P','GRC-2026-01-T')
  AND LOWER(o.notes) LIKE '%claril af%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-182','remove_incorrect_grecanico_destemming','wine_lot','GRC-2026-01',
       JSON_OBJECT('destemmed',FALSE,
                   'sequence',JSON_ARRAY('direct soft press','CLARIL AF must fining','first racking','alcoholic fermentation'))
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a
  WHERE a.estate_id=e.id AND a.actor='migration-182' AND a.action='remove_incorrect_grecanico_destemming'
);
