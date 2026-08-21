-- Current inventory is an operational balance and must not create historical-year shortages.
UPDATE issues_decisions
SET status='resolved',
    closed_date=COALESCE(closed_date,CURDATE()),
    decision_action='Closed by system audit: current inventory cannot establish a shortage for a historical treatment year.',
    notes=CONCAT_WS('\n',NULLIF(notes,''),'System audit 2026-08-21: historical shortage was generated from current stock and is not authoritative.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_issue_id='treatment-inventory-shortage:2025:vineyard'
  AND status IN ('open','monitoring');

-- This imported record concerns fermentation vessels and Clayver planning, not the sprayer.
UPDATE issues_decisions
SET subject_ref='2026 fermentation vessels and Clayver planning',
    issue_type='Cellar',
    issue_text='The 2026 fermentation-vessel plan is partly agreed, but exact available capacity, lot allocation and Clayver timing remain unconfirmed.',
    notes=CONCAT_WS('\n',NULLIF(notes,''),'System audit 2026-08-21: corrected mismatched sprayer/equipment classification; evidence and action are cellar planning.')
WHERE estate_id='00000000-0000-4000-8000-000000000001'
  AND source_issue_id='ISSUE-2026-015';

-- A paid invoice and its authoritative payment ledger must agree on the paid timestamp.
-- This repairs the six Giancarlo historical rows whose ledger was added after the older
-- status-only migration, and safely covers any equivalent fully paid legacy record.
UPDATE labor_entries labor
JOIN (
  SELECT estate_id,labor_entry_id,SUM(amount_eur) amount_paid,MAX(payment_date) last_payment_date
  FROM labor_invoice_payments
  WHERE voided_at IS NULL
  GROUP BY estate_id,labor_entry_id
) ledger ON ledger.estate_id=labor.estate_id AND ledger.labor_entry_id=labor.id
SET labor.paid_at=COALESCE(labor.paid_at,TIMESTAMP(ledger.last_payment_date))
WHERE labor.approval_status='approved'
  AND labor.payment_status='paid'
  AND labor.paid_at IS NULL
  AND ROUND(COALESCE(labor.labor_cost_eur,0)+COALESCE(labor.other_cost_eur,0),2)>0
  AND ledger.amount_paid>=ROUND(COALESCE(labor.labor_cost_eur,0)+COALESCE(labor.other_cost_eur,0),2);
