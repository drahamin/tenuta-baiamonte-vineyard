INSERT INTO labor_invoice_payments
  (id,estate_id,labor_entry_id,amount_eur,payment_date,payment_type,payment_method,payment_reference,notes,created_by)
SELECT UUID(),l.estate_id,l.id,
       ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2),
       DATE(COALESCE(l.paid_at,l.work_date,CURRENT_DATE)),
       'payment','legacy','MIGRATED-PAID-STATUS',
       'Payment ledger backfilled from the previously persisted paid status.',
       'migration-047'
FROM labor_entries l
WHERE l.approval_status='approved'
  AND l.payment_status='paid'
  AND ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2)>0
  AND NOT EXISTS (
    SELECT 1 FROM labor_invoice_payments p
    WHERE p.estate_id=l.estate_id AND p.labor_entry_id=l.id AND p.voided_at IS NULL
  );

UPDATE labor_entries l
JOIN (
  SELECT estate_id,labor_entry_id,SUM(amount_eur) amount_paid
  FROM labor_invoice_payments
  WHERE voided_at IS NULL
  GROUP BY estate_id,labor_entry_id
) paid ON paid.estate_id=l.estate_id AND paid.labor_entry_id=l.id
SET l.payment_status=CASE
      WHEN paid.amount_paid>=ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2) THEN 'paid'
      ELSE 'part_paid'
    END,
    l.paid_at=CASE
      WHEN paid.amount_paid>=ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2) THEN COALESCE(l.paid_at,CURRENT_TIMESTAMP)
      ELSE NULL
    END
WHERE l.approval_status='approved'
  AND paid.amount_paid>0
  AND ROUND(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0),2)>0;
