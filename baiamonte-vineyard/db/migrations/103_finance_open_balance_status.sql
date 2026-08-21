ALTER TABLE financial_documents
  ADD COLUMN IF NOT EXISTS source_paid_amount DECIMAL(16,2) NOT NULL DEFAULT 0 AFTER payment_status;

CREATE OR REPLACE VIEW v_finance_document_totals AS
SELECT d.id,d.estate_id,d.document_type,d.document_number,d.document_date,d.due_date,
       p.name party_name,d.taxable_amount,d.vat_amount,d.gross_total,d.payment_status,d.status,
       d.source,d.source_document,d.external_source_id,
       COALESCE(SUM(a.allocated_amount),0) allocated_cash,
       GREATEST(d.source_paid_amount,COALESCE(SUM(a.allocated_amount),0)) paid_amount,
       CASE WHEN d.payment_status='paid' THEN 0
            ELSE GREATEST(d.gross_total-GREATEST(d.source_paid_amount,COALESCE(SUM(a.allocated_amount),0)),0) END open_amount
FROM financial_documents d
LEFT JOIN finance_parties p ON p.id=d.party_id
LEFT JOIN cash_allocations a ON a.document_id=d.id
GROUP BY d.id,d.estate_id,d.document_type,d.document_number,d.document_date,d.due_date,p.name,
         d.taxable_amount,d.vat_amount,d.gross_total,d.payment_status,d.status,d.source,d.source_document,d.external_source_id;
