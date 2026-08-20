CREATE TABLE IF NOT EXISTS observation_photo_analyses (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  attachment_id CHAR(36) NOT NULL,
  entity_type ENUM('scouting','phenology','maturity_sample') NOT NULL,
  entity_id CHAR(36) NOT NULL,
  status ENUM('queued','processing','applied','review_required','failed') NOT NULL DEFAULT 'queued',
  model VARCHAR(120) NULL,
  confidence DECIMAL(6,5) NULL,
  analysis_json JSON NULL,
  applied_fields JSON NULL,
  review_reason TEXT NULL,
  error_message TEXT NULL,
  analyzed_at DATETIME(6) NULL,
  applied_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_observation_photo_attachment (attachment_id),
  KEY ix_observation_photo_record (estate_id,entity_type,entity_id,created_at),
  KEY ix_observation_photo_status (estate_id,status,created_at),
  CONSTRAINT fk_observation_photo_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_observation_photo_attachment FOREIGN KEY (attachment_id) REFERENCES entity_attachments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE scouting_observations
  ADD COLUMN damage_type VARCHAR(80) NULL AFTER incidence_pct,
  ADD COLUMN affected_area_pct DECIMAL(6,2) NULL AFTER damage_type,
  ADD COLUMN estimated_yield_loss_pct DECIMAL(6,2) NULL AFTER affected_area_pct,
  ADD COLUMN yield_impact_confidence ENUM('low','medium','high') NULL AFTER estimated_yield_loss_pct,
  ADD COLUMN yield_impact_source ENUM('manual','photo_ai','combined') NULL AFTER yield_impact_confidence,
  ADD COLUMN yield_impact_review_status ENUM('provisional','confirmed','rejected') NOT NULL DEFAULT 'provisional' AFTER yield_impact_source,
  ADD KEY ix_scouting_yield_impact (estate_id,season_id,damage_type,observed_at);
