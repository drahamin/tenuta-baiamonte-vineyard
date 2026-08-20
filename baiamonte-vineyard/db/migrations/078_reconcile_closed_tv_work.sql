UPDATE tasks
SET status='done', completed_at=COALESCE(completed_at,NOW(6))
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND status IN ('planned','in_progress')
  AND (LOWER(TRIM(title)) LIKE 'completato %' OR LOWER(TRIM(title)) LIKE 'completed %');

UPDATE tasks t
JOIN spray_applications s
  ON s.estate_id=t.estate_id
 AND LOWER(TRIM(t.title))=LOWER(TRIM(CONCAT('Treatment plan · ',s.purpose)))
 AND t.due_date=COALESCE(s.planned_application_date,DATE(s.application_date))
SET t.status=CASE
      WHEN s.status IN ('completed','applied') THEN 'done'
      WHEN s.status='cancelled' THEN 'cancelled'
      ELSE t.status
    END,
    t.completed_at=CASE
      WHEN s.status IN ('completed','applied') THEN COALESCE(t.completed_at,NOW(6))
      ELSE t.completed_at
    END
WHERE t.estate_id='00000000-0000-4000-8000-000000000001'
  AND t.category IN ('treatment','treatments','treatment_review','spray','spray_application')
  AND s.status IN ('completed','applied','cancelled');
