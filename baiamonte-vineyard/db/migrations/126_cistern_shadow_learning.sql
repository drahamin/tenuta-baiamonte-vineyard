CREATE TABLE IF NOT EXISTS cistern_learning_models (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  model_version VARCHAR(120) NOT NULL,
  model_status VARCHAR(40) NOT NULL DEFAULT 'learning',
  trained_at DATETIME(6) NOT NULL,
  data_through DATETIME NULL,
  observation_count INT UNSIGNED NOT NULL DEFAULT 0,
  backfill_case_count INT UNSIGNED NOT NULL DEFAULT 0,
  live_case_count INT UNSIGNED NOT NULL DEFAULT 0,
  parameters_snapshot JSON NULL,
  validation_metrics JSON NULL,
  data_quality_snapshot JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_cistern_learning_model (estate_id),
  CONSTRAINT fk_cistern_learning_model_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cistern_shadow_predictions (
  id CHAR(36) PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  target_estimate_id CHAR(36) NOT NULL,
  model_version VARCHAR(120) NOT NULL,
  prediction_kind VARCHAR(40) NOT NULL,
  generated_at DATETIME(6) NOT NULL,
  evidence_through DATETIME NOT NULL,
  prediction_for DATETIME NOT NULL,
  horizon_minutes INT UNSIGNED NOT NULL DEFAULT 0,
  predicted_level_percent DECIMAL(5,2) NOT NULL,
  observed_level_percent DECIMAL(5,2) NOT NULL,
  absolute_error_points DECIMAL(6,2) NOT NULL,
  evidence_snapshot JSON NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_cistern_shadow_target (estate_id,target_estimate_id,model_version),
  KEY ix_cistern_shadow_kind_time (estate_id,prediction_kind,prediction_for),
  CONSTRAINT fk_cistern_shadow_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE,
  CONSTRAINT fk_cistern_shadow_estimate FOREIGN KEY (target_estimate_id) REFERENCES cistern_level_estimates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
