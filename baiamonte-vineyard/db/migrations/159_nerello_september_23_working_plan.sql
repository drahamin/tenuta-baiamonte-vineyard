-- Owner's current expected Nerello Mascalese pick date. This is a protected
-- working plan, not a claim that the final enologist/agronomist decision is made.
INSERT INTO harvest_plans
  (id,estate_id,season_id,source_plan_id,variety_id,planned_pick_date,status,weather_risk,
   dependencies,approved_by,confidence,forecast_method,notes)
SELECT '15900000-0000-4000-8000-000000000001',e.id,s.id,'owner-2026-nerello-working-plan-0923',v.id,
       '2026-09-23','provisional','Continue checking rain, fruit condition and the current short-range forecast.',
       'Confirm representative fruit sample, latest enologist laboratory report, treatment clearance, crew and cellar readiness before picking.',
       'David Rahamin','medium','owner working harvest plan',
       'Owner expects harvest around September 23, 2026. Keep as the operational working date while laboratory, weather and field evidence continue to update.'
FROM estates e
JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN grape_varieties v ON v.estate_id=e.id AND LOWER(v.name) LIKE 'nerello%'
ON DUPLICATE KEY UPDATE planned_pick_date=VALUES(planned_pick_date),status=VALUES(status),weather_risk=VALUES(weather_risk),
  dependencies=VALUES(dependencies),approved_by=VALUES(approved_by),confidence=VALUES(confidence),
  forecast_method=VALUES(forecast_method),notes=VALUES(notes),updated_at=NOW(6);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-159','set_working_plan','harvest_plan','owner-2026-nerello-working-plan-0923',
       JSON_OBJECT('variety','Nerello Mascalese','planned_pick_date','2026-09-23','status','provisional',
                   'basis','Owner working expectation; continue lab, weather and field review')
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-159' AND a.entity_id='owner-2026-nerello-working-plan-0923');
