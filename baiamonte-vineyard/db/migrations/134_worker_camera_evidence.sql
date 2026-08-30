CREATE TABLE IF NOT EXISTS worker_camera_evidence (
  id CHAR(64) NOT NULL,
  estate_id CHAR(36) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  observation_zone VARCHAR(80) NOT NULL DEFAULT 'estate',
  captured_at DATETIME(6) NOT NULL,
  source_kind VARCHAR(80) NOT NULL,
  content_type VARCHAR(80) NOT NULL,
  original_bytes BIGINT UNSIGNED NOT NULL,
  encrypted_bytes BIGINT UNSIGNED NOT NULL,
  width_px INT UNSIGNED NULL,
  height_px INT UNSIGNED NULL,
  storage_path VARCHAR(500) NOT NULL,
  retention_until DATETIME(6) NOT NULL,
  legal_hold TINYINT(1) NOT NULL DEFAULT 0,
  review_status ENUM('unreviewed','confirmed','rejected') NOT NULL DEFAULT 'unreviewed',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_worker_camera_evidence_retention (estate_id,legal_hold,retention_until),
  KEY ix_worker_camera_evidence_time (estate_id,camera_entity_id,captured_at),
  CONSTRAINT fk_worker_camera_evidence_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE worker_vehicle_event_checks
  ADD COLUMN IF NOT EXISTS evidence_id CHAR(64) NULL AFTER frame_sha256;
