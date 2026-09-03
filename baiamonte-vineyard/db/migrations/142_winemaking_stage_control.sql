-- Enologist-controlled progress through the complete winemaking workflow.
-- Derived readiness remains advisory; complete/skipped stages require enology approval.
CREATE TABLE IF NOT EXISTS enology_stage_events (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  stage_code VARCHAR(80) NOT NULL,
  stage_status ENUM('not_started','ready','in_progress','blocked','complete','held','skipped') NOT NULL DEFAULT 'not_started',
  planned_at DATETIME(6) NULL,
  completed_at DATETIME(6) NULL,
  notes TEXT NULL,
  approved_by VARCHAR(190) NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_enology_lot_stage (estate_id,wine_lot_id,stage_code),
  KEY ix_enology_stage_status (estate_id,stage_status,updated_at),
  CONSTRAINT fk_enology_stage_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_enology_stage_lot FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
