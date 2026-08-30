CREATE TABLE IF NOT EXISTS worker_vehicle_event_checks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  estate_id CHAR(36) NOT NULL,
  camera_entity_id VARCHAR(255) NOT NULL,
  event_image_entity_id VARCHAR(255) NULL,
  detected_at VARCHAR(80) NULL,
  frame_sha256 CHAR(64) NOT NULL,
  vehicle_visible BOOLEAN NOT NULL DEFAULT FALSE,
  matched_observations INT UNSIGNED NOT NULL DEFAULT 0,
  event_types JSON NULL,
  checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_worker_vehicle_event_frame (estate_id,camera_entity_id,frame_sha256),
  KEY ix_worker_vehicle_event_time (estate_id,checked_at),
  CONSTRAINT fk_worker_vehicle_event_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
