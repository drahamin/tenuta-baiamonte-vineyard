CREATE TABLE IF NOT EXISTS entity_attachments (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id CHAR(36) NOT NULL,
  original_filename VARCHAR(255) NOT NULL,
  stored_path VARCHAR(700) NOT NULL,
  media_type VARCHAR(120) NULL,
  file_sha256 CHAR(64) NOT NULL,
  caption VARCHAR(500) NULL,
  uploaded_by VARCHAR(160) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_entity_attachment (estate_id,entity_type,entity_id),
  CONSTRAINT fk_attachment_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
