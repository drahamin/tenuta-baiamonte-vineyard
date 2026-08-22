ALTER TABLE disease_pressure_assessments
  ADD COLUMN base_risk_score DECIMAL(6,2) NULL AFTER disease_name,
  ADD COLUMN calibration_adjustment DECIMAL(6,2) NOT NULL DEFAULT 0 AFTER risk_score,
  ADD COLUMN learning_model_version VARCHAR(80) NULL AFTER model_version,
  ADD COLUMN agronomist_risk_score DECIMAL(6,2) NULL AFTER agronomist_status,
  ADD COLUMN agronomist_risk_level ENUM('low','moderate','high','critical') NULL AFTER agronomist_risk_score;

UPDATE disease_pressure_assessments SET base_risk_score=risk_score WHERE base_risk_score IS NULL;

CREATE TABLE IF NOT EXISTS disease_pressure_learning_cases (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  assessment_id CHAR(36) NOT NULL,
  disease_code VARCHAR(80) NOT NULL,
  assessment_date DATE NOT NULL,
  base_risk_score DECIMAL(6,2) NOT NULL,
  target_risk_score DECIMAL(6,2) NOT NULL,
  label_source ENUM('agronomist_review','field_scouting') NOT NULL,
  evidence_weight DECIMAL(5,2) NOT NULL DEFAULT 1,
  evidence_snapshot JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_disease_learning_assessment_source (assessment_id,label_source),
  KEY ix_disease_learning_training (estate_id,disease_code,assessment_date),
  CONSTRAINT fk_disease_learning_case_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_disease_learning_case_assessment FOREIGN KEY (assessment_id) REFERENCES disease_pressure_assessments(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS disease_pressure_learning_models (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  model_version VARCHAR(80) NOT NULL,
  trained_at DATETIME(6) NOT NULL,
  data_through DATE NULL,
  training_case_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  agronomist_case_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  scouting_case_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  season_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  disease_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  model_status VARCHAR(40) NOT NULL,
  parameters_snapshot JSON NOT NULL,
  validation_metrics JSON NOT NULL,
  data_quality_snapshot JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_disease_learning_model_version (estate_id,model_version),
  KEY ix_disease_learning_model_current (estate_id,trained_at),
  CONSTRAINT fk_disease_learning_model_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
