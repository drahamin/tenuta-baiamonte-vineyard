CREATE TABLE IF NOT EXISTS hospitality_partners (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  name VARCHAR(220) NOT NULL,
  partner_type ENUM('travel_agent','travel_advisor','hotel','concierge','event_planner','tour_operator','restaurant','venue','other') NOT NULL DEFAULT 'other',
  contact_name VARCHAR(180) NULL,
  email VARCHAR(320) NULL,
  phone VARCHAR(80) NULL,
  tax_id VARCHAR(100) NULL,
  payment_details TEXT NULL,
  default_commission_type ENUM('percentage','fixed_per_guest','fixed_per_reservation') NOT NULL DEFAULT 'percentage',
  default_commission_value DECIMAL(12,4) NOT NULL DEFAULT 0,
  payment_terms_days SMALLINT UNSIGNED NOT NULL DEFAULT 30,
  active TINYINT(1) NOT NULL DEFAULT 1,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_hospitality_partner_name (estate_id,name),
  KEY ix_hospitality_partner_active (estate_id,active,name),
  CONSTRAINT fk_hospitality_partner_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE hospitality_reservations
  ADD COLUMN partner_id CHAR(36) NULL AFTER package_id,
  ADD COLUMN partner_referral_code VARCHAR(100) NULL AFTER partner_id,
  ADD KEY ix_hospitality_reservation_partner (estate_id,partner_id,start_at),
  ADD CONSTRAINT fk_hospitality_reservation_partner FOREIGN KEY (partner_id) REFERENCES hospitality_partners(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS hospitality_partner_commissions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  partner_id CHAR(36) NOT NULL,
  reservation_id CHAR(36) NOT NULL,
  basis_amount_eur DECIMAL(16,2) NOT NULL DEFAULT 0,
  commission_type ENUM('percentage','fixed_per_guest','fixed_per_reservation') NOT NULL,
  commission_value DECIMAL(12,4) NOT NULL DEFAULT 0,
  commission_amount_eur DECIMAL(16,2) NOT NULL DEFAULT 0,
  status ENUM('estimated','due','approved','partially_paid','paid','void') NOT NULL DEFAULT 'estimated',
  due_date DATE NULL,
  approved_by VARCHAR(190) NULL,
  approved_at DATETIME(6) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_hospitality_commission_reservation (reservation_id),
  KEY ix_hospitality_commission_queue (estate_id,status,due_date),
  KEY ix_hospitality_commission_partner (partner_id,status,due_date),
  CONSTRAINT fk_hospitality_commission_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_hospitality_commission_partner FOREIGN KEY (partner_id) REFERENCES hospitality_partners(id),
  CONSTRAINT fk_hospitality_commission_reservation FOREIGN KEY (reservation_id) REFERENCES hospitality_reservations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS hospitality_partner_payments (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  partner_id CHAR(36) NOT NULL,
  commission_id CHAR(36) NOT NULL,
  amount_eur DECIMAL(16,2) NOT NULL,
  paid_on DATE NOT NULL,
  method VARCHAR(80) NULL,
  reference VARCHAR(160) NULL,
  notes TEXT NULL,
  recorded_by VARCHAR(190) NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  KEY ix_hospitality_partner_payment (estate_id,partner_id,paid_on),
  KEY ix_hospitality_commission_payment (commission_id,paid_on),
  CONSTRAINT fk_hospitality_partner_payment_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_hospitality_partner_payment_partner FOREIGN KEY (partner_id) REFERENCES hospitality_partners(id),
  CONSTRAINT fk_hospitality_partner_payment_commission FOREIGN KEY (commission_id) REFERENCES hospitality_partner_commissions(id) ON DELETE CASCADE,
  CONSTRAINT ck_hospitality_partner_payment_positive CHECK (amount_eur > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
