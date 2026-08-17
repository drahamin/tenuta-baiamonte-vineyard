CREATE TABLE IF NOT EXISTS cellar_control_profiles (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  container_id CHAR(36) NOT NULL,
  reading_mode ENUM('manual','sensor') NOT NULL DEFAULT 'manual',
  sensor_status ENUM('not_configured','configured','live','stale','fault','maintenance') NOT NULL DEFAULT 'not_configured',
  manual_contents VARCHAR(255) NULL,
  manual_volume_l DECIMAL(12,3) NULL,
  manual_stage VARCHAR(80) NULL,
  manual_temp_c DECIMAL(7,3) NULL,
  manual_density_sg DECIMAL(8,5) NULL,
  manual_brix DECIMAL(7,3) NULL,
  manual_ph DECIMAL(6,3) NULL,
  manual_reading_at DATETIME(6) NULL,
  manual_updated_at DATETIME(6) NULL,
  last_maintenance_at DATETIME(6) NULL,
  next_maintenance_at DATETIME(6) NULL,
  maintenance_notes TEXT NULL,
  updated_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_cellar_control_container (estate_id, container_id),
  KEY ix_cellar_control_mode (estate_id, reading_mode),
  CONSTRAINT fk_cellar_control_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellar_control_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO cellar_control_profiles (id, estate_id, container_id, reading_mode, sensor_status, updated_by)
SELECT UUID(), c.estate_id, c.id, 'manual', 'not_configured', 'migration-030'
FROM cellar_containers c
LEFT JOIN cellar_control_profiles cp ON cp.estate_id=c.estate_id AND cp.container_id=c.id
WHERE cp.id IS NULL;

-- Release 1.1.0 promotes the current estate tank inventory to authoritative
-- manual records. A tank may subsequently be changed to sensor mode from the
-- Agronomy workspace once its Home Assistant mapping is configured.
UPDATE cellar_control_profiles cp
JOIN cellar_containers c ON c.id=cp.container_id AND c.estate_id=cp.estate_id
SET cp.reading_mode='manual', cp.sensor_status='not_configured', cp.updated_by='migration-030-manual'
WHERE c.active=1;

CREATE TABLE IF NOT EXISTS cellar_maintenance_records (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  container_id CHAR(36) NOT NULL,
  maintenance_at DATETIME(6) NOT NULL,
  maintenance_type VARCHAR(120) NOT NULL,
  status ENUM('planned','in_progress','completed') NOT NULL DEFAULT 'completed',
  performed_by VARCHAR(190) NULL,
  next_due_at DATETIME(6) NULL,
  notes TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_cellar_maintenance_container (estate_id, container_id, maintenance_at),
  CONSTRAINT fk_cellar_maintenance_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellar_maintenance_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS treatment_program_reviews (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  reviewed_at DATETIME(6) NOT NULL,
  review_status ENUM('reviewed','changes_required','approved') NOT NULL DEFAULT 'reviewed',
  reviewer VARCHAR(190) NULL,
  scope_text VARCHAR(255) NULL,
  notes TEXT NULL,
  next_review_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_treatment_program_review (estate_id, season_id, reviewed_at),
  CONSTRAINT fk_treatment_program_review_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_program_review_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cellar_lot_trace_records (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  season_id CHAR(36) NOT NULL,
  harvest_lot_id CHAR(36) NOT NULL,
  wine_lot_id CHAR(36) NOT NULL,
  container_id CHAR(36) NOT NULL,
  transferred_at DATETIME(6) NOT NULL,
  fruit_kg DECIMAL(12,3) NULL,
  must_l DECIMAL(12,3) NULL,
  notes TEXT NULL,
  recorded_by VARCHAR(190) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_cellar_trace_tank (estate_id, container_id, transferred_at),
  KEY ix_cellar_trace_harvest (estate_id, harvest_lot_id),
  CONSTRAINT fk_cellar_trace_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellar_trace_season FOREIGN KEY (season_id) REFERENCES seasons(id) ON DELETE CASCADE,
  CONSTRAINT fk_cellar_trace_harvest FOREIGN KEY (harvest_lot_id) REFERENCES harvest_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cellar_trace_wine FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cellar_trace_container FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
