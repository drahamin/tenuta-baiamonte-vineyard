UPDATE tasks t
JOIN (
  SELECT DISTINCT estate_id,task_id
  FROM work_item_links
  WHERE active=1 AND LOWER(COALESCE(source_status,'')) IN ('completed','done','closed')
) completed_source ON completed_source.estate_id=t.estate_id AND completed_source.task_id=t.id
SET t.status='done',t.completed_at=COALESCE(t.completed_at,CURRENT_TIMESTAMP)
WHERE t.status NOT IN ('done','cancelled');
