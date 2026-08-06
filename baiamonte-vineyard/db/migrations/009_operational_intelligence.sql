CREATE TABLE IF NOT EXISTS disease_pressure_assessments (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  assessed_at DATETIME(6) NOT NULL,
  assessment_date DATE NOT NULL,
  model_version VARCHAR(40) NOT NULL,
  disease_code VARCHAR(80) NOT NULL,
  disease_name VARCHAR(160) NOT NULL,
  risk_score DECIMAL(6,2) NOT NULL,
  risk_level ENUM('low','moderate','high','critical') NOT NULL,
  evidence_summary TEXT NOT NULL,
  suggested_action TEXT NOT NULL,
  agronomist_status ENUM('pending','approved','modified','rejected','not_required') NOT NULL DEFAULT 'pending',
  agronomist_name VARCHAR(160) NULL,
  agronomist_notes TEXT NULL,
  reviewed_at DATETIME(6) NULL,
  input_snapshot JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_pressure_day_disease (estate_id,assessment_date,disease_code),
  KEY ix_pressure_date (estate_id,assessment_date,risk_level),
  CONSTRAINT fk_pressure_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS intake_items (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  source ENUM('upload','gmail','whatsapp','codex','chatgpt','home_assistant') NOT NULL,
  external_id VARCHAR(255) NULL,
  sender_name VARCHAR(180) NULL,
  sender_address VARCHAR(255) NULL,
  received_at DATETIME(6) NOT NULL,
  title VARCHAR(300) NULL,
  message_text MEDIUMTEXT NULL,
  original_filename VARCHAR(255) NULL,
  stored_path VARCHAR(700) NULL,
  media_type VARCHAR(160) NULL,
  file_sha256 CHAR(64) NULL,
  classification VARCHAR(80) NULL,
  extracted_data JSON NULL,
  ai_summary MEDIUMTEXT NULL,
  review_status ENUM('new','processing','ready_for_review','approved','rejected','failed') NOT NULL DEFAULT 'new',
  reviewed_by VARCHAR(180) NULL,
  reviewed_at DATETIME(6) NULL,
  processing_error TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_intake_external (estate_id,source,external_id),
  KEY ix_intake_status_date (estate_id,review_status,received_at),
  CONSTRAINT fk_intake_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS lab_result_revisions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  result_id CHAR(36) NOT NULL,
  changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  changed_by VARCHAR(180) NOT NULL,
  reason VARCHAR(500) NOT NULL,
  before_data JSON NOT NULL,
  after_data JSON NOT NULL,
  KEY ix_lab_revision_result (result_id,changed_at),
  CONSTRAINT fk_lab_revision_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_lab_revision_result FOREIGN KEY (result_id) REFERENCES lab_results(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sync_checkpoints (
  estate_id CHAR(36) NOT NULL,
  integration_name VARCHAR(100) NOT NULL,
  checkpoint_value VARCHAR(500) NULL,
  last_success_at DATETIME(6) NULL,
  last_attempt_at DATETIME(6) NULL,
  last_error TEXT NULL,
  metadata JSON NULL,
  PRIMARY KEY (estate_id,integration_name),
  CONSTRAINT fk_checkpoint_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS planning_sensor_snapshots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  entity_id VARCHAR(255) NOT NULL,
  recorded_at DATETIME(6) NOT NULL,
  state_value VARCHAR(255) NULL,
  numeric_value DECIMAL(18,6) NULL,
  unit VARCHAR(80) NULL,
  friendly_name VARCHAR(255) NULL,
  source VARCHAR(80) NOT NULL DEFAULT 'home_assistant',
  attributes JSON NULL,
  UNIQUE KEY uq_planning_sensor_time (estate_id,entity_id,recorded_at),
  KEY ix_planning_sensor_date (estate_id,recorded_at),
  CONSTRAINT fk_planning_sensor_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE OR REPLACE VIEW v_treatment_history AS
SELECT a.id,a.estate_id,a.application_date,a.purpose,a.area_ha,a.water_volume_l,a.operator_name,
       a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,b.code block_code,b.name block_name,
       a.agronomist_approved,a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,
       a.ppe_confirmed,a.actual_details_confirmed,
       GROUP_CONCAT(CONCAT(p.name,' ',i.dose_amount,' ',i.dose_unit) ORDER BY p.name SEPARATOR ' | ') products,
       MAX(i.phi_days) phi_days
FROM spray_applications a
LEFT JOIN vineyard_blocks b ON b.id=a.block_id
LEFT JOIN spray_application_items i ON i.application_id=a.id
LEFT JOIN products p ON p.id=i.product_id
GROUP BY a.id,a.estate_id,a.application_date,a.purpose,a.area_ha,a.water_volume_l,a.operator_name,
         a.equipment_name,a.temp_c,a.wind_kph,a.status,a.notes,b.code,b.name,a.agronomist_approved,
         a.label_legal_confirmed,a.phi_checked,a.rei_checked,a.weather_checked,a.ppe_confirmed,a.actual_details_confirmed;
