CREATE TABLE IF NOT EXISTS prediction_source_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_code VARCHAR(60) NOT NULL,
  scope_type VARCHAR(30) NOT NULL DEFAULT 'estate',
  scope_id VARCHAR(80) NOT NULL DEFAULT 'estate',
  status VARCHAR(30) NOT NULL,
  role_code VARCHAR(40) NOT NULL,
  observed_at DATETIME(6) NULL,
  valid_from DATE NULL,
  valid_through DATE NULL,
  payload JSON NOT NULL,
  source_url VARCHAR(700) NULL,
  error_message VARCHAR(500) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_prediction_source_latest (estate_id,source_code,scope_type,scope_id,created_at),
  KEY ix_prediction_source_validity (estate_id,valid_through,status),
  CONSTRAINT fk_prediction_source_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
