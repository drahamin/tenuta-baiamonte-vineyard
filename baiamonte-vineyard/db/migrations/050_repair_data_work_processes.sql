UPDATE tasks t
JOIN spray_applications s
  ON s.estate_id=t.estate_id
 AND s.status IN ('completed','applied')
 AND t.category IN ('treatment','treatments','treatment_review','spray','spray_application')
 AND LOWER(TRIM(t.title))=LOWER(TRIM(CONCAT('Treatment plan · ',s.purpose)))
 AND (t.due_date=COALESCE(s.planned_application_date,DATE(s.application_date)) OR t.due_date IS NULL)
SET t.status='done',
    t.completed_at=COALESCE(t.completed_at,s.application_date,CURRENT_TIMESTAMP)
WHERE t.status IN ('planned','in_progress');
