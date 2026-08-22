CREATE TABLE IF NOT EXISTS treatment_scouting_links (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  application_id CHAR(36) NOT NULL,
  observation_id CHAR(36) NOT NULL,
  phase ENUM('pre','post') NOT NULL,
  target_code VARCHAR(80) NULL,
  link_method ENUM('explicit','automatic') NOT NULL DEFAULT 'explicit',
  linked_by VARCHAR(160) NULL,
  linked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_treatment_scouting_observation (application_id, observation_id),
  KEY ix_treatment_scouting_application_phase (application_id, phase),
  KEY ix_treatment_scouting_observation (observation_id),
  CONSTRAINT fk_treatment_scouting_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_scouting_application FOREIGN KEY (application_id) REFERENCES spray_applications(id) ON DELETE CASCADE,
  CONSTRAINT fk_treatment_scouting_observation FOREIGN KEY (observation_id) REFERENCES scouting_observations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
