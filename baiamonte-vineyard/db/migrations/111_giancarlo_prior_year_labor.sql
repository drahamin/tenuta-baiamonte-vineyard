-- Owner-authorized 2026-08-22 operational backfill from the existing Proclama
-- payroll archive. Preserve monthly precision: the source supports 988 hours
-- from December 2024 through October 2025 and 15 worked days in November 2025,
-- but it does not state November hours. The owner confirmed all of this prior
-- labor was paid; known-value rows receive matching historical ledger entries.

INSERT IGNORE INTO labor_entries
  (id,estate_id,season_id,person_id,source_labor_id,work_date,shift_label,
   person_or_crew,role,regular_hours,overtime_hours,hourly_rate_eur,
   labor_cost_eur,approved_by,payment_status,paid_at,pay_due_date,payroll_scope,notes,
   work_category,work_performed,entry_source,worker_username,approval_status)
SELECT UUID(),source.estate_id,season.id,person.id,
       CONCAT('HISTORICAL-COST:',source.id),source.record_date,
       CONCAT('Monthly source total · ',source.source_sheet),source.actor_name,
       'Estate manager',source.labor_hours,
       CASE WHEN source.labor_hours IS NULL THEN NULL ELSE 0 END,
       CASE WHEN source.labor_hours IS NULL THEN NULL ELSE 10.00 END,
       CASE WHEN source.labor_hours IS NULL THEN NULL ELSE ROUND(source.labor_hours*10.00,2) END,
       'Owner-authorized historical backfill','paid',
       TIMESTAMP(DATE_ADD(LAST_DAY(source.record_date),INTERVAL 15 DAY)),
       DATE_ADD(LAST_DAY(source.record_date),INTERVAL 15 DAY),'part_time',
       CONCAT(source.description,' · Source: ',source.source_file_name,' / ',source.source_sheet,
              '. Owner confirmed this prior labor was paid. November 2025 hours and amount remain unknown when absent from the source.'),
       'historical_attendance',source.description,'historical_import','giancarlo','approved'
FROM historical_cost_records source
LEFT JOIN seasons season
  ON season.estate_id=source.estate_id AND season.vintage_year=source.record_year
LEFT JOIN (
  SELECT estate_id,MIN(id) id FROM people
  WHERE LOWER(TRIM(name))='giancarlo pafumi' GROUP BY estate_id
) person ON person.estate_id=source.estate_id
WHERE source.estate_id='00000000-0000-4000-8000-000000000001'
  AND source.source_file_id='gmail-proclama-giancarlo'
  AND LOWER(TRIM(source.actor_name))='giancarlo pafumi'
  AND source.classification='payroll_labor'
  AND source.record_date BETWEEN '2024-12-01' AND '2025-11-30';

INSERT INTO labor_invoice_payments
  (id,estate_id,labor_entry_id,amount_eur,payment_date,payment_type,
   payment_method,payment_reference,notes,created_by)
SELECT UUID(),labor.estate_id,labor.id,labor.labor_cost_eur,
       DATE_ADD(LAST_DAY(labor.work_date),INTERVAL 15 DAY),'payment',
       'historical reconciliation','GIANCARLO-PAID-PRIOR-YEARS',
       'Owner confirmed all prior-year Giancarlo labor was paid; payment date follows the recorded prior-month payroll schedule.',
       'migration-111'
FROM labor_entries labor
WHERE labor.source_labor_id LIKE 'HISTORICAL-COST:%'
  AND labor.person_or_crew='Giancarlo Pafumi'
  AND labor.work_date BETWEEN '2024-12-01' AND '2025-11-30'
  AND labor.labor_cost_eur>0
  AND NOT EXISTS (
    SELECT 1 FROM labor_invoice_payments payment
    WHERE payment.estate_id=labor.estate_id
      AND payment.labor_entry_id=labor.id
      AND payment.voided_at IS NULL
  );

INSERT INTO audit_events
  (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT labor.estate_id,'migration-111','backfill','labor',labor.id,NULL,
       JSON_OBJECT(
         'source_labor_id',labor.source_labor_id,
         'person_or_crew',labor.person_or_crew,
         'work_date',labor.work_date,
         'regular_hours',labor.regular_hours,
         'hourly_rate_eur',labor.hourly_rate_eur,
         'labor_cost_eur',labor.labor_cost_eur,
         'payment_status',labor.payment_status,
         'source_basis','Existing Proclama payroll archive; owner-authorized operational backfill 2026-08-22'
       )
FROM labor_entries labor
WHERE labor.source_labor_id LIKE 'HISTORICAL-COST:%'
  AND labor.person_or_crew='Giancarlo Pafumi'
  AND labor.work_date BETWEEN '2024-12-01' AND '2025-11-30'
  AND NOT EXISTS (
    SELECT 1 FROM audit_events audit
    WHERE audit.actor='migration-111' AND audit.action='backfill'
      AND audit.entity_type='labor' AND audit.entity_id=labor.id
  );
