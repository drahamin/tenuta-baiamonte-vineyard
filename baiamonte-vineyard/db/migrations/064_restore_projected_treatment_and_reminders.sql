-- The owner confirmed on 2026-08-19 that Treatment 5 was projected, not done.
-- Preserve the former assertion in the notes for auditability, then append the
-- authoritative correction and restore the application to the planned state.
INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT s.estate_id,'owner-correction','restore_projected','treatment',s.id,
       JSON_OBJECT('purpose',s.purpose,'status',s.status,'application_date',s.application_date,'actual_details_confirmed',s.actual_details_confirmed),
       JSON_OBJECT('purpose',s.purpose,'status','planned','planned_application_date',COALESCE(s.planned_application_date,DATE(s.application_date)),'reason','Treatment 5 was projected and was not completed')
FROM spray_applications s
WHERE LOWER(TRIM(s.purpose))='treatment 5'
  AND s.status='completed'
  AND s.actual_details_confirmed=0
  AND LOWER(COALESCE(s.notes,'')) LIKE '%completion confirmed by user%'
  AND COALESCE(s.notes,'') NOT LIKE '%[USER:2026-08-19 | Treatment 5 was projected and was not completed; restored to planned]%';

UPDATE spray_applications
SET planned_application_date=COALESCE(planned_application_date,DATE(application_date)),
    status='planned',
    actual_details_confirmed=0,
    notes=CONCAT_WS('\n\n',NULLIF(notes,''),'[USER:2026-08-19 | Treatment 5 was projected and was not completed; restored to planned]')
WHERE LOWER(TRIM(purpose))='treatment 5'
  AND status='completed'
  AND actual_details_confirmed=0
  AND LOWER(COALESCE(notes,'')) LIKE '%completion confirmed by user%'
  AND COALESCE(notes,'') NOT LIKE '%[USER:2026-08-19 | Treatment 5 was projected and was not completed; restored to planned]%';

-- A treatment reminder follows the authoritative spray record. A checked-off
-- reminder alone is never evidence that the application occurred.
UPDATE tasks t
JOIN spray_applications s
  ON s.estate_id=t.estate_id
 AND LOWER(TRIM(t.title))=LOWER(TRIM(CONCAT('Treatment plan · ',s.purpose)))
 AND (t.due_date=COALESCE(s.planned_application_date,DATE(s.application_date)) OR t.due_date IS NULL)
SET t.status='planned',t.completed_at=NULL
WHERE LOWER(TRIM(s.purpose))='treatment 5'
  AND s.status='planned'
  AND t.status='done';

-- Repair canonical Google-imported reminders that were closed only because a
-- different linked source was stale-completed while Google still says open.
UPDATE tasks t
JOIN work_item_links g
  ON g.estate_id=t.estate_id AND g.task_id=t.id AND g.active=1
 AND g.source_type='google_tasks'
 AND LOWER(COALESCE(g.source_status,'')) NOT IN ('completed','done','closed')
JOIN work_item_links other_source
  ON other_source.estate_id=t.estate_id AND other_source.task_id=t.id AND other_source.active=1
 AND other_source.source_type<>'google_tasks'
 AND LOWER(COALESCE(other_source.source_status,'')) IN ('completed','done','closed')
SET t.status='planned',t.completed_at=NULL
WHERE t.source='google_tasks'
  AND t.status='done'
  AND NOT EXISTS (
    SELECT 1 FROM work_item_links completed_google
    WHERE completed_google.estate_id=t.estate_id
      AND completed_google.task_id=t.id
      AND completed_google.active=1
      AND completed_google.source_type='google_tasks'
      AND LOWER(COALESCE(completed_google.source_status,'')) IN ('completed','done','closed')
  );
