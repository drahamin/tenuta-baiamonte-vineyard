CREATE TABLE IF NOT EXISTS camera_ai_comparisons (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  feature_code VARCHAR(80) NOT NULL,
  local_provider VARCHAR(80) NOT NULL,
  local_decision VARCHAR(120) NULL,
  reference_decision VARCHAR(120) NULL,
  agreed TINYINT(1) NOT NULL DEFAULT 0,
  local_failed TINYINT(1) NOT NULL DEFAULT 0,
  reference_failed TINYINT(1) NOT NULL DEFAULT 0,
  evidence_key VARCHAR(190) NULL,
  metadata JSON NULL,
  observed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY ix_camera_ai_comparison_time (estate_id, observed_at),
  KEY ix_camera_ai_comparison_feature (estate_id, feature_code, observed_at),
  CONSTRAINT fk_camera_ai_comparison_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS camera_ai_weekly_checks (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  estate_id CHAR(36) NOT NULL,
  checked_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  comparisons INT UNSIGNED NOT NULL DEFAULT 0,
  agreement_pct DECIMAL(6,2) NULL,
  local_failure_pct DECIMAL(6,2) NULL,
  eligible TINYINT(1) NOT NULL DEFAULT 0,
  notes VARCHAR(500) NULL,
  KEY ix_camera_ai_weekly_time (estate_id, checked_at),
  CONSTRAINT fk_camera_ai_weekly_estate FOREIGN KEY (estate_id) REFERENCES estates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO app_settings (estate_id,setting_key,setting_value)
SELECT id,'camera_ai_policy',JSON_OBJECT(
  'shadow_enabled',TRUE,
  'weekly_check_enabled',TRUE,
  'primary_requested',FALSE,
  'enabled_at',DATE_FORMAT(UTC_TIMESTAMP(6),'%Y-%m-%dT%H:%i:%s.%f'),
  'primary_not_before',DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 DAY),'%Y-%m-%dT%H:%i:%s.%f'),
  'updated_by','migration-138'
) FROM estates
ON DUPLICATE KEY UPDATE setting_key=VALUES(setting_key);
