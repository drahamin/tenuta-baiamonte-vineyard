CREATE TABLE IF NOT EXISTS estate_vehicle_plate_reads (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source_key CHAR(64) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  frame_sha256 CHAR(64) NOT NULL,
  vehicle_identity_key VARCHAR(128) NULL,
  plate_pattern VARCHAR(16) NULL,
  plate_country VARCHAR(80) NULL,
  confidence_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
  observed_at DATETIME(6) NOT NULL,
  evidence_id CHAR(64) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_estate_vehicle_plate_source (estate_id,source_key),
  KEY ix_estate_vehicle_plate_learning (estate_id,vehicle_identity_key,observed_at),
  CONSTRAINT fk_estate_vehicle_plate_read_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
