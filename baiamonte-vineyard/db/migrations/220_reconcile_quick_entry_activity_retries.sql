-- The source-link failure on 2026-10-17 happened after the work row had been
-- committed, so two retries created exact copies. Preserve the first record
-- and an explicit audit trail while removing only the two verified retry IDs.
INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT estate_id,'system-reconciliation','remove_retry_duplicate','work_activity',id,
       JSON_OBJECT('title',title,'activity_date',activity_date,'created_at',created_at),
       JSON_OBJECT('canonical_id','4b127519-bf99-4a73-9032-1175619a9f54','reason','Exact retry after source-link failure')
FROM work_activities
WHERE id IN ('3d9e89ce-8b4d-4ac1-903e-9f84e1e5982a','31c7c0f4-e372-4721-8260-8a719497c753')
  AND title='Excavator work by Nunzio' AND activity_date='2026-10-17';

DELETE FROM work_activities
WHERE id IN ('3d9e89ce-8b4d-4ac1-903e-9f84e1e5982a','31c7c0f4-e372-4721-8260-8a719497c753')
  AND title='Excavator work by Nunzio' AND activity_date='2026-10-17';
