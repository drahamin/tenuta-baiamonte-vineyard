-- Preserve any legacy invalid row for audit while removing it from every
-- active-ledger total before the constraint is enabled.
UPDATE labor_invoice_payments
SET voided_at=COALESCE(voided_at,NOW(6)),
    voided_by=COALESCE(voided_by,'migration:invalid-payment-amount')
WHERE amount_eur<=0 AND voided_at IS NULL;

-- Application validation remains the friendly first line of defense. Historical
-- voided rows may remain visible to auditors, but every active payment must be
-- strictly positive.
ALTER TABLE labor_invoice_payments
  ADD CONSTRAINT chk_labor_invoice_payment_positive CHECK (amount_eur > 0 OR voided_at IS NOT NULL);
