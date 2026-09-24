ALTER TABLE harvest_plans
  ADD COLUMN IF NOT EXISTS planned_pick_window VARCHAR(40) NULL AFTER planned_pick_date;

INSERT INTO harvest_plans
  (id,estate_id,season_id,source_plan_id,variety_id,planned_pick_date,planned_pick_window,status,weather_risk,
   dependencies,approved_by,confidence,forecast_method,notes)
SELECT '15900000-0000-4000-8000-000000000001',e.id,s.id,'owner-2026-nerello-working-plan-0923',v.id,
       '2026-09-25','morning','confirmed','Check the current short-range forecast before crew departure.',
       'Crew, crates and cellar reception ready for the morning harvest.',
       'David Rahamin','high','owner confirmed harvest schedule',
       'Owner confirmed Nerello Mascalese harvest for the morning of September 25, 2026.'
FROM estates e
JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN grape_varieties v ON v.estate_id=e.id AND LOWER(v.name) LIKE 'nerello%'
ON DUPLICATE KEY UPDATE planned_pick_date=VALUES(planned_pick_date),planned_pick_window=VALUES(planned_pick_window),
  status=VALUES(status),weather_risk=VALUES(weather_risk),dependencies=VALUES(dependencies),approved_by=VALUES(approved_by),
  confidence=VALUES(confidence),forecast_method=VALUES(forecast_method),notes=VALUES(notes),updated_at=NOW(6);

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-175','confirm_harvest_schedule','harvest_plan','owner-2026-nerello-working-plan-0923',
       JSON_OBJECT('variety','Nerello Mascalese','planned_pick_date','2026-09-25','planned_pick_window','morning',
                   'status','confirmed','approved_by','David Rahamin')
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-175' AND a.entity_id='owner-2026-nerello-working-plan-0923');
