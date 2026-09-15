-- Source-backed reconciliation supplied by the owner from Giancarlo's two
-- photographed sheets. Rates and payment status were not stated, so hours and
-- service charges remain verification-needed rather than inventing payroll.

INSERT IGNORE INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,person_or_crew,role,regular_hours,overtime_hours,
   payment_status,payroll_scope,notes,work_category,work_performed,location_text,entry_source,
   approval_status,locked_at,review_note)
SELECT source.id,e.id,s.id,source.source_labor_id,source.work_date,source.person_or_crew,
       'Seasonal vineyard worker',source.hours,0,'verification_needed','unknown',
       'Giancarlo reconciliation supplied by David Rahamin; exact hours transcribed from the photographed sheet. Rate and payment were not stated.',
       'hourly_labor',source.work_performed,'Tenuta Baiamonte','giancarlo_reconciliation','approved',NOW(6),
       'Source-backed hours approved as an estate record; compensation still requires verification.'
FROM estates e
JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN (
  SELECT '15800000-0000-4000-8000-000000000001' id,'GIANCARLO-2026-CRISTIAN-0811' source_labor_id,'2026-08-11' work_date,'Cristian' person_or_crew,8 hours,'August vineyard work' work_performed UNION ALL
  SELECT '15800000-0000-4000-8000-000000000002','GIANCARLO-2026-CRISTIAN-0812','2026-08-12','Cristian',10,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000003','GIANCARLO-2026-CRISTIAN-0813','2026-08-13','Cristian',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000004','GIANCARLO-2026-CRISTIAN-0820','2026-08-20','Cristian',4,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000005','GIANCARLO-2026-CRISTIAN-0821','2026-08-21','Cristian',4,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000006','GIANCARLO-2026-CRISTIAN-0826','2026-08-26','Cristian',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000007','GIANCARLO-2026-CRISTIAN-0827','2026-08-27','Cristian',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000008','GIANCARLO-2026-CRISTIAN-0828','2026-08-28','Cristian',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000009','GIANCARLO-2026-CRISTIAN-0831','2026-08-31','Cristian',5,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000010','GIANCARLO-2026-COSTANZA-0820','2026-08-20','Costanza',4,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000011','GIANCARLO-2026-COSTANZA-0821','2026-08-21','Costanza',4,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000012','GIANCARLO-2026-COSTANZA-0826','2026-08-26','Costanza',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000013','GIANCARLO-2026-COSTANZA-0827','2026-08-27','Costanza',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000014','GIANCARLO-2026-COSTANZA-0828','2026-08-28','Costanza',6,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000015','GIANCARLO-2026-COSTANZA-0831','2026-08-31','Costanza',5,'August vineyard work' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000016','GIANCARLO-2026-CRISTIAN-GRECANICO','2026-09-09','Cristian',8,'Grecanico harvest' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000017','GIANCARLO-2026-COSTANZA-GRECANICO','2026-09-09','Costanza',8,'Grecanico harvest' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000018','GIANCARLO-2026-NUNZIO-GRECANICO','2026-09-09','Nunzio',8,'Grecanico harvest' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000019','GIANCARLO-2026-CRISTIAN-GRENACHE','2026-09-10','Cristian',3,'Grenache harvest' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000020','GIANCARLO-2026-COSTANZA-GRENACHE','2026-09-10','Costanza',3,'Grenache harvest' UNION ALL
  SELECT '15800000-0000-4000-8000-000000000021','GIANCARLO-2026-COSTANZA-BROTHER-GRENACHE','2026-09-10','Costanza''s brother',3,'Grenache harvest'
) source ON 1=1;

INSERT IGNORE INTO labor_entries
  (id,estate_id,season_id,source_labor_id,work_date,person_or_crew,role,regular_hours,overtime_hours,
   labor_cost_eur,other_cost_eur,payment_status,payroll_scope,notes,work_category,work_performed,
   location_text,entry_source,approval_status,locked_at,review_note,expense_amount_eur,expense_category,expense_notes)
SELECT source.id,e.id,s.id,source.source_labor_id,source.work_date,'Nunzio','Transport service',0,0,
       0,source.amount,'verification_needed','payroll_excluded',
       'Giancarlo reconciliation supplied by David Rahamin. The exact service amount is recorded; payment method and paid status were not stated.',
       'one_off_charge',source.work_performed,'Tenuta Baiamonte','giancarlo_reconciliation','approved',NOW(6),
       'Service charge approved as an estate record; payment remains to be verified.',source.amount,'transport',source.work_performed
FROM estates e
JOIN seasons s ON s.estate_id=e.id AND s.vintage_year=2026
JOIN (
  SELECT '15800000-0000-4000-8000-000000000022' id,'GIANCARLO-2026-NUNZIO-WATER-0903' source_labor_id,'2026-09-03' work_date,80 amount,'One water transport trip' work_performed UNION ALL
  SELECT '15800000-0000-4000-8000-000000000023','GIANCARLO-2026-NUNZIO-CRATES-0911','2026-09-11',120,'Crate transport'
) source ON 1=1;

UPDATE labor_entries
SET notes=CONCAT(COALESCE(notes,''),CASE WHEN COALESCE(notes,'')='' THEN '' ELSE ' ' END,
  'Giancarlo reconciliation identifies Cristian, Costanza and Nunzio at 8 h each; 3 of the 6 crew members remain unnamed.')
WHERE source_labor_id='wendy-2026-grecanico-harvest-crew'
  AND COALESCE(notes,'') NOT LIKE '%3 of the 6 crew members remain unnamed%';

UPDATE labor_entries
SET notes=CONCAT(COALESCE(notes,''),CASE WHEN COALESCE(notes,'')='' THEN '' ELSE ' ' END,
  'Giancarlo reconciliation identifies Cristian, Costanza and Costanza''s brother at 3 h each; 1 of the 4 crew members remains unnamed.')
WHERE source_labor_id='wendy-2026-grenache-harvest-crew'
  AND COALESCE(notes,'') NOT LIKE '%1 of the 4 crew members remains unnamed%';

INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data)
SELECT e.id,'migration-158','reconcile','labor','giancarlo-2026-reconciliation',
       JSON_OBJECT('cristian_august_hours',55,'costanza_august_hours',31,
                   'grecanico_named_workers',3,'grecanico_unresolved_workers',3,
                   'grenache_named_workers',3,'grenache_unresolved_workers',1,
                   'nunzio_service_charges_eur',200,'payment_status','verification_needed')
FROM estates e
WHERE NOT EXISTS (SELECT 1 FROM audit_events a WHERE a.estate_id=e.id AND a.actor='migration-158' AND a.entity_id='giancarlo-2026-reconciliation');
