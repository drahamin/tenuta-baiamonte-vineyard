-- Owner-confirmed: Giancarlo was paid in full through 2026-07-31.
-- The six imported monthly rows were marked paid before the audited payment
-- ledger existed; backfill exactly their approved invoice amounts once.
INSERT INTO labor_invoice_payments
  (id,estate_id,labor_entry_id,amount_eur,payment_date,payment_type,payment_method,payment_reference,notes,created_by)
SELECT UUID(),l.estate_id,l.id,
       ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2),
       LEAST(l.work_date,'2026-07-31'),'payment','historical reconciliation',
       'GIANCARLO-PAID-THROUGH-2026-07-31',
       'Owner-confirmed paid in full through July 31, 2026; backfilled when the payment ledger became authoritative.',
       'migration-104'
FROM labor_entries l
WHERE l.source_labor_id LIKE 'HISTORICAL-GIANCARLO-2026-%-MONTHLY'
  AND l.work_date<='2026-07-31'
  AND l.approval_status='approved'
  AND l.payment_status='paid'
  AND COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0)>0
  AND NOT EXISTS (
    SELECT 1 FROM labor_invoice_payments p
    WHERE p.estate_id=l.estate_id AND p.labor_entry_id=l.id AND p.voided_at IS NULL
  );
