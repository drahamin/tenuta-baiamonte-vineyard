ALTER TABLE labor_entries MODIFY COLUMN payment_status ENUM('unknown','unpaid','verification_needed','part_paid','paid') NOT NULL DEFAULT 'unknown';

CREATE TABLE IF NOT EXISTS labor_invoice_payments (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  labor_entry_id CHAR(36) NOT NULL,
  amount_eur DECIMAL(12,2) NOT NULL,
  payment_date DATE NOT NULL,
  payment_type ENUM('deposit','payment') NOT NULL DEFAULT 'payment',
  payment_method VARCHAR(80) NULL,
  payment_reference VARCHAR(180) NULL,
  notes TEXT NULL,
  created_by VARCHAR(120) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  voided_at DATETIME(6) NULL,
  voided_by VARCHAR(120) NULL,
  INDEX idx_labor_invoice_payments_entry (estate_id,labor_entry_id,payment_date),
  CONSTRAINT fk_labor_invoice_payment_entry FOREIGN KEY (labor_entry_id) REFERENCES labor_entries(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
