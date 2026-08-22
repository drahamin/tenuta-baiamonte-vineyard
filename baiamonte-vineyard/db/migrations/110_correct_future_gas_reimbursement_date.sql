-- Owner-authorized correction of the sole future-dated labor record.
-- The archived July timesheet contains reimbursements dated July 15, July 22,
-- and an erroneous August 27. The final entry is July 27; preserve the paid
-- amount and payment history while correcting both operational and source data.

INSERT INTO audit_events
  (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT estate_id,'migration-110','correct_date','labor',id,
       JSON_OBJECT(
         'work_date',work_date,
         'person_or_crew',person_or_crew,
         'work_performed',work_performed,
         'other_cost_eur',other_cost_eur,
         'payment_status',payment_status,
         'source_labor_id',source_labor_id
       ),
       JSON_OBJECT(
         'work_date','2026-07-27',
         'person_or_crew',person_or_crew,
         'work_performed',work_performed,
         'other_cost_eur',other_cost_eur,
         'payment_status',payment_status,
         'source_labor_id',source_labor_id,
         'correction_basis','Approved July timesheet chronology; August month was entered in error'
       )
FROM labor_entries
WHERE id='4461108a-1603-4f21-b4bf-bef5e019997e'
  AND source_labor_id='3ad302dc-4b00-4bbc-9eba-b60fffe7b53f:expense:2'
  AND work_date='2026-08-27'
  AND work_performed='Gas'
  AND other_cost_eur=20;

UPDATE labor_entries
SET work_date='2026-07-27',
    notes=CONCAT_WS(' · ',NULLIF(notes,''),'Date corrected from 2026-08-27 to 2026-07-27 by migration 110; amount and paid status unchanged.')
WHERE id='4461108a-1603-4f21-b4bf-bef5e019997e'
  AND source_labor_id='3ad302dc-4b00-4bbc-9eba-b60fffe7b53f:expense:2'
  AND work_date='2026-08-27'
  AND work_performed='Gas'
  AND other_cost_eur=20;

INSERT INTO audit_events
  (estate_id,actor,action,entity_type,entity_id,before_data,after_data)
SELECT estate_id,'migration-110','correct_source_date','intake',id,
       JSON_OBJECT(
         'title',title,
         'expense_date',JSON_UNQUOTE(JSON_EXTRACT(extracted_data,'$.reimbursable_expenses[1].expense_date'))
       ),
       JSON_OBJECT(
         'title','Giancarlo — July 2026 labor hours (139 h)',
         'expense_date','2026-07-27',
         'correction_basis','Approved July timesheet chronology; August month was entered in error'
       )
FROM intake_items
WHERE id='3ad302dc-4b00-4bbc-9eba-b60fffe7b53f'
  AND JSON_UNQUOTE(JSON_EXTRACT(extracted_data,'$.reimbursable_expenses[1].expense_date'))='2026-08-27';

UPDATE intake_items
SET title='Giancarlo — July 2026 labor hours (139 h)',
    extracted_data=JSON_SET(extracted_data,'$.reimbursable_expenses[1].expense_date','2026-07-27'),
    review_reason=CONCAT_WS(' · ',NULLIF(review_reason,''),'Source date corrected from 2026-08-27 to 2026-07-27 by migration 110.')
WHERE id='3ad302dc-4b00-4bbc-9eba-b60fffe7b53f'
  AND JSON_UNQUOTE(JSON_EXTRACT(extracted_data,'$.reimbursable_expenses[1].expense_date'))='2026-08-27';
