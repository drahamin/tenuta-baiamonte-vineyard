-- Recorded estate picking is authoritative over the provisional 2026 plan.
-- Preserve the original planned quantities for audit, but close the working
-- proposals and align their operational date with the actual picking record.

UPDATE harvest_plans p
JOIN seasons s ON s.id=p.season_id AND s.vintage_year=2026
JOIN grape_varieties v ON v.id=p.variety_id
JOIN (
  SELECT h.season_id,h.variety_id,MIN(DATE(h.harvested_at)) actual_pick_date,
         SUM(h.weight_kg) actual_estate_kg
  FROM harvest_lots h
  WHERE h.source_type='estate_harvest'
  GROUP BY h.season_id,h.variety_id
) actual ON actual.season_id=p.season_id AND actual.variety_id=p.variety_id
SET p.status='complete',
    p.planned_pick_date=actual.actual_pick_date,
    p.confidence='high',
    p.forecast_method='completed harvest record overrides forecast',
    p.notes=CONCAT_WS('\n',NULLIF(p.notes,''),
      CONCAT('Completed harvest record is authoritative: ',DATE_FORMAT(actual.actual_pick_date,'%e %M %Y'),
             '; ',FORMAT(actual.actual_estate_kg,2),' kg estate fruit recorded. The retained planned quantity is historical forecast evidence, not remaining fruit.'))
WHERE LOWER(TRIM(v.name)) IN ('grecanico','grenache')
  AND p.status NOT IN ('complete','cancelled','canceled')
  AND COALESCE(p.notes,'') NOT LIKE '%Completed harvest record is authoritative:%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-212','complete_harvest_plans_from_actuals','season','2026',
       JSON_OBJECT(
         'authoritative_source','harvest_lots',
         'completed_varieties',JSON_ARRAY('Grecanico','Grenache'),
         'grecanico_actual_estate_kg',2299.53,
         'grenache_actual_estate_kg',399.25,
         'rule','Completed estate picking records override provisional plans in operational feeds; original plan quantities remain audit history.'
       )
FROM estates e
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-212'
    AND a.action='complete_harvest_plans_from_actuals'
);
