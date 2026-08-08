CREATE TABLE IF NOT EXISTS cistern_level_estimates (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  observed_at DATETIME NOT NULL,
  level_percent DECIMAL(5,2) NOT NULL,
  confidence DECIMAL(5,2) NULL,
  source VARCHAR(40) NOT NULL DEFAULT 'camera_estimate',
  camera_entity_id VARCHAR(255) NULL,
  model VARCHAR(120) NULL,
  notes TEXT NULL,
  image_sha256 CHAR(64) NULL,
  metadata JSON NULL,
  INDEX idx_cistern_level_estate_time (estate_id, observed_at),
  CONSTRAINT fk_cistern_level_estate FOREIGN KEY (estate_id) REFERENCES estates(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
