-- Schema-only successor to retired 235. No business records are created or changed.
CREATE TABLE IF NOT EXISTS enology_mlf_plans (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  product_name VARCHAR(160) NOT NULL DEFAULT 'LALVIN VP41 MBR',
  formulation VARCHAR(40) NOT NULL DEFAULT 'MBR',
  timing_plan VARCHAR(40) NOT NULL DEFAULT 'sequential',
  volume_min_l DECIMAL(12,3) NULL,
  volume_max_l DECIMAL(12,3) NULL,
  volume_basis VARCHAR(40) NOT NULL,
  volume_basis_note VARCHAR(700) NOT NULL,
  small_sachet_coverage_l DECIMAL(12,3) NOT NULL DEFAULT 250,
  large_sachet_coverage_l DECIMAL(12,3) NOT NULL DEFAULT 2500,
  exact_label_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  suitability_confirmed TINYINT(1) NOT NULL DEFAULT 0,
  approved_by VARCHAR(160) NULL,
  notes TEXT NULL,
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_mlf_plan_lot (wine_lot_id),
  CONSTRAINT fk_enology_mlf_plan_estate FOREIGN KEY (estate_id) REFERENCES estates(id),
  CONSTRAINT fk_enology_mlf_plan_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
