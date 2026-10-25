CREATE TABLE IF NOT EXISTS vintage_designation_plan_source_lots (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  plan_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  component_role ENUM('nerello','grenache') NOT NULL,
  available_volume_l_snapshot DECIMAL(12,3) NOT NULL DEFAULT 0,
  allocated_volume_l_snapshot DECIMAL(12,3) NOT NULL DEFAULT 0,
  remaining_volume_l_snapshot DECIMAL(12,3) NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_designation_plan_source_lot (plan_id,wine_lot_id),
  KEY ix_designation_source_lot (estate_id,wine_lot_id),
  CONSTRAINT fk_designation_source_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_designation_source_plan FOREIGN KEY (plan_id) REFERENCES vintage_designation_plans(id) ON DELETE CASCADE,
  CONSTRAINT fk_designation_source_wine_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
